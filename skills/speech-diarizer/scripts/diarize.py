#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["whisperx>=3.3"]
# ///
"""
diarize.py — accurate speaker-diarized transcription with WhisperX + pyannote.

Usage:
    uv run diarize.py meeting.m4a
    uv run diarize.py interview.wav --num-speakers 2 --language en
    uv run diarize.py call.mp3 --min-speakers 2 --max-speakers 5 -o ./transcripts

Requires a Hugging Face token (env HF_TOKEN, --hf-token, or a cached `hf auth login`),
with the gated pyannote repos accepted.
Outputs: <name>.md (speaker-labeled, the default deliverable); --srt and --json add
those extras. Per-run speaker embeddings are cached for enroll.py.
"""

import argparse
import datetime as dt
import gc
import json
import os
import sys
from pathlib import Path

# make the sibling voiceprints module importable when run via `uv run --script`
sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Speaker-diarized transcription (WhisperX + pyannote).")
    p.add_argument("audio", nargs="+", help="Audio file(s): wav, mp3, m4a, etc.")
    p.add_argument("--model", default="large-v3", help="Whisper model (default: large-v3)")
    p.add_argument("--language", default=None, help="Language code like 'en'; omit to auto-detect")
    p.add_argument("--num-speakers", type=int, default=None, help="Exact speaker count, if known")
    p.add_argument("--min-speakers", type=int, default=None)
    p.add_argument("--max-speakers", type=int, default=None)
    p.add_argument(
        "--diarization-model",
        default="pyannote/speaker-diarization-3.1",
        help="pyannote pipeline (try pyannote/speaker-diarization-community-1 if your "
        "whisperx ships pyannote.audio>=4)",
    )
    p.add_argument("--batch-size", type=int, default=8, help="Transcription batch size")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"), help="Hugging Face token (default: $HF_TOKEN)")
    p.add_argument("-o", "--output-dir", default=None,
                   help="Output directory (default: $SPEECH_DIARIZER_OUTPUT_DIR or ~/Documents/transcriptions)")
    p.add_argument("--no-identify", dest="identify", action="store_false",
                   help="skip matching speakers against the enrolled voiceprint store")
    p.add_argument("--threshold", type=float, default=0.5,
                   help="cosine similarity needed to attach an enrolled name (default: 0.5)")
    p.add_argument("--store", default=None,
                   help="voiceprint store path (default: $SPEECH_DIARIZER_VOICEPRINTS or ~/.config/speech-diarizer/voiceprints.json)")
    p.add_argument("--srt", action="store_true", help="also write a .srt subtitle file")
    p.add_argument("--json", action="store_true", help="also write the full word-level .json")
    p.set_defaults(identify=True)
    return p.parse_args()


def pick_devices():
    """ctranslate2 (transcription) is CPU-only on macOS; pyannote can use MPS."""
    import torch

    asr_device = "cuda" if torch.cuda.is_available() else "cpu"
    if torch.cuda.is_available():
        diar_device = torch.device("cuda")
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        diar_device = torch.device("mps")
    else:
        diar_device = torch.device("cpu")
    compute_type = "float16" if asr_device == "cuda" else "int8"
    return asr_device, diar_device, compute_type


def get_diarization_pipeline(model_name: str, token: str, device):
    """whisperx moved DiarizationPipeline and renamed its token kwarg between versions."""
    import inspect

    try:
        from whisperx.diarize import DiarizationPipeline  # whisperx >= 3.2-ish
    except ImportError:
        from whisperx import DiarizationPipeline  # older layout

    params = inspect.signature(DiarizationPipeline.__init__).parameters
    kwargs = {"model_name": model_name, "device": device}
    # newer whisperx (pyannote.audio>=4) uses `token`; older used `use_auth_token`
    if "token" in params:
        kwargs["token"] = token
    elif "use_auth_token" in params:
        kwargs["use_auth_token"] = token
    return DiarizationPipeline(**kwargs)


def merge_turns(segments: list[dict]) -> list[dict]:
    """Merge consecutive segments by the same speaker into readable turns."""
    turns: list[dict] = []
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "").strip()
        if not text:
            continue
        if turns and turns[-1]["speaker"] == speaker:
            turns[-1]["text"] += " " + text
            turns[-1]["end"] = seg["end"]
        else:
            turns.append({"speaker": speaker, "start": seg["start"], "end": seg["end"], "text": text})
    return turns


def fmt_clock(seconds: float) -> str:
    """compact clock: m:ss under an hour, h:mm:ss past it."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def fmt_srt(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_markdown(result: dict, out_base: Path, meta: dict) -> Path:
    """the primary deliverable: frontmatter + clean speaker-labeled turns."""
    turns = merge_turns(result["segments"])
    speakers = meta["speakers"]
    unknown = [s for s in speakers if s.startswith("SPEAKER_")]
    named = [s for s in speakers if not s.startswith("SPEAKER_")]

    fm = [
        "---",
        f"source: {json.dumps(meta['source'])}",
        f"generated: {json.dumps(meta['generated'])}",
        f"duration: {json.dumps(meta['duration'])}",
        f"language: {json.dumps(meta['language'])}",
        f"speakers: {json.dumps(speakers, ensure_ascii=False)}",
        f"transcription_model: {json.dumps(meta['transcription_model'])}",
        f"diarization_model: {json.dumps(meta['diarization_model'])}",
        "---",
        "",
        f"# {out_base.stem}",
        "",
        f"{len(speakers)} speakers · {meta['duration']} · {meta['transcription_model']} + {meta['diarization_model'].split('/')[-1]}",
    ]
    if unknown:
        line = ""
        if named:
            line += f"identified: {', '.join(named)}"
        line += f"{' — ' if named else ''}unrecognized: {', '.join(unknown)} (enroll with enroll.py to name)"
        fm.append(line)
    fm.append("")

    body = [f"**[{fmt_clock(t['start'])}] {t['speaker']}:** {t['text'].strip()}" for t in turns]
    md_path = out_base.with_suffix(".md")
    md_path.write_text("\n".join(fm) + "\n" + "\n\n".join(body) + "\n", encoding="utf-8")
    return md_path


def write_srt(result: dict, out_base: Path) -> Path:
    blocks = []
    for i, seg in enumerate(s for s in result["segments"] if s.get("text", "").strip()):
        speaker = seg.get("speaker", "UNKNOWN")
        blocks.append(
            f"{i + 1}\n{fmt_srt(seg['start'])} --> {fmt_srt(seg['end'])}\n"
            f"[{speaker}] {seg['text'].strip()}\n"
        )
    srt_path = out_base.with_suffix(".srt")
    srt_path.write_text("\n".join(blocks), encoding="utf-8")
    return srt_path


def write_json(result: dict, out_base: Path) -> Path:
    json_path = out_base.with_suffix(".json")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def identify_speakers(speaker_embeddings: dict, model: str, threshold: float, store_arg: str | None):
    """match diarized speakers against the enrolled voiceprint store.

    returns (name_map, detail): name_map is {SPEAKER_XX: name} for confident matches only;
    detail is the full per-speaker scoring, persisted to the sidecar.
    """
    from voiceprints import identify as vp_identify
    from voiceprints import load_store

    store = load_store(store_arg)
    if not store["speakers"]:
        print("      no enrolled voiceprints yet - speakers stay anonymous (use enroll.py to name them)")
        return {}, {}
    if store.get("model") and store["model"] != model:
        print(f"      WARNING: store was built with {store['model']} but this run used {model}; "
              "skipping identification (embeddings are not comparable across models)")
        return {}, {}

    results = vp_identify(speaker_embeddings, store, threshold)
    name_map: dict[str, str] = {}
    detail: dict[str, dict] = {}
    for spk, info in results.items():
        scores = info["scores"]
        detail[spk] = {
            "name": info["name"],
            "similarity": round(info["similarity"], 4),
            "scores": [[round(s, 4), n] for s, n in scores[:3]],
        }
        if info["name"]:
            name_map[spk] = info["name"]
            print(f"      {spk} -> {info['name']} (sim {info['similarity']:.3f})")
        else:
            top = f"{scores[0][1]} {scores[0][0]:.3f}" if scores else "none"
            print(f"      {spk} -> [unknown] (closest: {top}, below {threshold})")
    return name_map, detail


def cache_voiceprints(stem: str, source_name: str, args, speaker_embeddings: dict, detail: dict) -> Path | None:
    """stash this run's raw per-speaker embeddings in the cache so enroll.py can name them later.

    kept out of the output dir on purpose - it's machinery, not a deliverable.
    """
    if not speaker_embeddings:
        return None
    from voiceprints import cache_dir

    data = {
        "source": source_name,
        "diarization_model": args.diarization_model,
        "threshold": args.threshold,
        "raw_embeddings": {spk: [float(x) for x in emb] for spk, emb in speaker_embeddings.items()},
        "identified": detail,
    }
    path = cache_dir() / f"{stem}.voiceprints.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def process_file(path: Path, args, asr_device, diar_device, compute_type) -> None:
    import whisperx

    print(f"\n=== {path.name} ===")

    print(f"[1/4] Transcribing with {args.model} on {asr_device} ({compute_type})...")
    model = whisperx.load_model(args.model, device=asr_device, compute_type=compute_type, language=args.language)
    audio = whisperx.load_audio(str(path))
    result = model.transcribe(audio, batch_size=args.batch_size, language=args.language)
    language = result["language"]
    print(f"      language: {language}, segments: {len(result['segments'])}")
    del model
    gc.collect()

    print("[2/4] Aligning word timestamps...")
    align_model, metadata = whisperx.load_align_model(language_code=language, device=asr_device)
    result = whisperx.align(
        result["segments"], align_model, metadata, audio, asr_device, return_char_alignments=False
    )
    del align_model
    gc.collect()

    print(f"[3/4] Diarizing with {args.diarization_model} on {diar_device}...")
    diarizer = get_diarization_pipeline(args.diarization_model, args.hf_token, diar_device)
    diarize_kwargs = {}
    if args.num_speakers:
        diarize_kwargs["num_speakers"] = args.num_speakers
    if args.min_speakers:
        diarize_kwargs["min_speakers"] = args.min_speakers
    if args.max_speakers:
        diarize_kwargs["max_speakers"] = args.max_speakers
    diarize_kwargs["return_embeddings"] = True
    diarize_segments, speaker_embeddings = diarizer(audio, **diarize_kwargs)

    # fill_nearest=True assigns the closest speaker to segments with no direct diarization
    # overlap, instead of leaving them as "UNKNOWN" (common on short interjections/crosstalk)
    result = whisperx.assign_word_speakers(diarize_segments, result, fill_nearest=True)
    result["language"] = language
    speakers = sorted({s.get("speaker", "UNKNOWN") for s in result["segments"]})
    print(f"      speakers found: {', '.join(speakers)}")

    # identify speakers against enrolled voiceprints and relabel matches in-place
    name_map, detail = ({}, {})
    if args.identify and speaker_embeddings:
        name_map, detail = identify_speakers(speaker_embeddings, args.diarization_model, args.threshold, args.store)
        if name_map:
            for seg in result["segments"]:
                spk = seg.get("speaker")
                if spk in name_map:
                    seg["speaker"] = name_map[spk]

    print("[4/4] Writing outputs...")
    # centralized default so transcriptions don't scatter next to their source files;
    # -o overrides, then $SPEECH_DIARIZER_OUTPUT_DIR, else ~/Documents/transcriptions
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = Path(os.environ.get("SPEECH_DIARIZER_OUTPUT_DIR",
                                      Path.home() / "Documents" / "transcriptions"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_base = out_dir / path.stem

    # final speaker labels in first-appearance order (names where identified, else SPEAKER_XX)
    turns = merge_turns(result["segments"])
    seen, ordered = set(), []
    for t in turns:
        if t["speaker"] not in seen:
            seen.add(t["speaker"])
            ordered.append(t["speaker"])
    meta = {
        "source": path.name,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "duration": fmt_clock(len(audio) / 16000),
        "language": language,
        "speakers": ordered,
        "transcription_model": args.model,
        "diarization_model": args.diarization_model,
    }

    # the deliverable: one clean markdown file
    print(f"      {write_markdown(result, out_base, meta)}")
    # extras only on request
    if args.srt:
        print(f"      {write_srt(result, out_base)}")
    if args.json:
        print(f"      {write_json(result, out_base)}")
    # embeddings cached out of the way for later enrollment
    cached = cache_voiceprints(path.stem, path.name, args, speaker_embeddings, detail)
    if cached and not name_map:
        print(f"      (voiceprints cached - name speakers with: enroll.py {path.stem} SPEAKER_XX=Name)")


def resolve_token(explicit: str | None) -> str | None:
    """prefer an explicit token / $HF_TOKEN, else fall back to the cached `hf auth login`."""
    if explicit:
        return explicit
    try:
        from huggingface_hub import get_token

        return get_token()
    except Exception:
        return None


def main() -> None:
    args = parse_args()

    args.hf_token = resolve_token(args.hf_token)
    if not args.hf_token:
        sys.exit(
            "Error: no Hugging Face token. Log in once with `hf auth login`, or set HF_TOKEN "
            "in your shell (see https://huggingface.co/settings/tokens), or pass --hf-token. "
            "Also make sure you've accepted the gates on the pyannote model pages."
        )

    paths = [Path(a) for a in args.audio]
    missing = [p for p in paths if not p.exists()]
    if missing:
        sys.exit(f"Error: file(s) not found: {', '.join(map(str, missing))}")

    asr_device, diar_device, compute_type = pick_devices()

    for path in paths:
        try:
            process_file(path, args, asr_device, diar_device, compute_type)
        except Exception as e:
            msg = str(e)
            if "401" in msg or "403" in msg or "gated" in msg.lower():
                sys.exit(
                    f"Access error for {args.diarization_model}: your token works but the model "
                    "gate likely isn't accepted. Visit the model page on huggingface.co while "
                    "logged in and click 'Agree and access repository'. Original error:\n" + msg
                )
            raise

    print("\nDone.")


if __name__ == "__main__":
    main()
