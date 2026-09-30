import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_UPLOAD_BYTES = 24 * 1024 * 1024
DEFAULT_MODEL = "gpt-4o-transcribe"
DEFAULT_LOCAL_MODEL = "small"
FALLBACK_CHUNK_SECONDS = 20 * 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="transcribe a local video or audio file into markdown"
    )
    parser.add_argument("media_path", help="absolute or relative path to a video or audio file")
    parser.add_argument(
        "--output",
        help="optional markdown output path. defaults to ai-agents-config/transcriptions/<stem>.md",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI transcription model (cloud) or whisper model name (local). default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--language",
        help="optional language hint such as en or ar",
    )
    parser.add_argument(
        "--prompt",
        help="optional short hint with names or jargon to improve recognition (cloud only)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=f"use local openai-whisper instead of the OpenAI API. default model: {DEFAULT_LOCAL_MODEL}",
    )
    parser.add_argument(
        "--segments",
        action="store_true",
        help="also write a '## segments' section with [mm:ss] timestamps (local backend only)",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_command(command_name: str) -> str:
    command_path = shutil.which(command_name)
    if not command_path:
        fail(f"missing required command: {command_name}")
    return command_path


def resolve_workspace_root(script_path: Path) -> Path:
    for parent in script_path.parents:
        if parent.name == "skills":
            return parent.parent
    fail("could not resolve workspace root from script location")
    raise AssertionError("unreachable")


def sanitize_stem(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._")
    return sanitized or "transcript"


def unique_output_path(output_path: Path) -> Path:
    if not output_path.exists():
        return output_path

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return output_path.with_name(f"{output_path.stem}-{timestamp}{output_path.suffix}")


def default_output_path(media_path: Path, workspace_root: Path) -> Path:
    transcriptions_dir = workspace_root / "transcriptions"
    transcriptions_dir.mkdir(parents=True, exist_ok=True)
    base_name = sanitize_stem(media_path.stem)
    return unique_output_path(transcriptions_dir / f"{base_name}.md")


def resolve_output_path(output_arg: str | None, media_path: Path, workspace_root: Path) -> Path:
    if not output_arg:
        return default_output_path(media_path, workspace_root)

    output_path = Path(output_arg).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return unique_output_path(output_path)


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or str(exc)
        fail(f"command failed: {' '.join(args)}\n{details}")


def extract_audio(media_path: Path, output_path: Path) -> None:
    ffmpeg_path = require_command("ffmpeg")
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "48k",
        str(output_path),
    ]
    run_command(command)


def get_media_duration_seconds(media_path: Path) -> float | None:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    result = run_command(command)
    output = result.stdout.strip()
    if not output:
        return None

    try:
        return float(output)
    except ValueError:
        return None


def chunk_seconds_from_size(audio_size_bytes: int, duration_seconds: float | None) -> int:
    if not duration_seconds or duration_seconds <= 0:
        return FALLBACK_CHUNK_SECONDS

    bytes_per_second = audio_size_bytes / duration_seconds
    if bytes_per_second <= 0:
        return FALLBACK_CHUNK_SECONDS

    safe_target_bytes = int(MAX_UPLOAD_BYTES * 0.85)
    estimated_chunk_seconds = int(safe_target_bytes / bytes_per_second)
    return max(5 * 60, estimated_chunk_seconds)


def extract_audio_chunks(media_path: Path, temp_dir: Path) -> list[Path]:
    single_audio_path = temp_dir / "audio.mp3"
    extract_audio(media_path, single_audio_path)

    if single_audio_path.stat().st_size <= MAX_UPLOAD_BYTES:
        return [single_audio_path]

    duration_seconds = get_media_duration_seconds(media_path)
    chunk_seconds = chunk_seconds_from_size(
        audio_size_bytes=single_audio_path.stat().st_size,
        duration_seconds=duration_seconds,
    )
    single_audio_path.unlink(missing_ok=True)

    ffmpeg_path = require_command("ffmpeg")
    chunk_pattern = temp_dir / "chunk-%03d.mp3"
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "48k",
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        str(chunk_pattern),
    ]
    run_command(command)

    chunk_paths = sorted(temp_dir.glob("chunk-*.mp3"))
    if not chunk_paths:
        fail("ffmpeg did not produce any audio chunks")

    oversize_chunks = [path.name for path in chunk_paths if path.stat().st_size > MAX_UPLOAD_BYTES]
    if oversize_chunks:
        fail(
            "audio chunks still exceed the upload limit: "
            + ", ".join(oversize_chunks)
            + ". lower the bitrate or chunk duration."
        )

    return chunk_paths


# -- local whisper --

def transcribe_local(
    media_path: Path,
    model_name: str,
    language: str | None,
) -> tuple[str, list[str]]:
    try:
        import whisper
    except ImportError:
        fail(
            "python dependency missing: openai-whisper. run "
            "'uv pip install -r speech-video-transcriber/scripts/requirements.txt'"
        )

    print(f"loading local whisper model: {model_name}", file=sys.stderr)
    model = whisper.load_model(model_name)

    kwargs: dict = {}
    if language:
        kwargs["language"] = language

    print("transcribing...", file=sys.stderr)
    result = model.transcribe(str(media_path), **kwargs)
    text = result.get("text", "")
    if not text:
        fail("local whisper returned no text")

    # one line per whisper segment: [mm:ss] text
    segment_lines: list[str] = []
    for segment in result.get("segments", []):
        start = int(segment.get("start", 0))
        minutes, seconds = divmod(start, 60)
        segment_text = str(segment.get("text", "")).strip()
        if segment_text:
            segment_lines.append(f"[{minutes:02d}:{seconds:02d}] {segment_text}")
    return text.strip(), segment_lines


# -- cloud openai --

def create_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        fail("OPENAI_API_KEY is not set")

    try:
        from openai import OpenAI
    except ImportError as exc:
        fail(
            "python dependency missing: openai. run "
            "'uv pip install -r speech-video-transcriber/scripts/requirements.txt'"
        )
        raise exc

    return OpenAI(api_key=api_key)


def transcribe_chunks(
    chunk_paths: list[Path],
    model: str,
    language: str | None,
    prompt: str | None,
) -> str:
    client = create_client()
    transcripts: list[str] = []

    for index, chunk_path in enumerate(chunk_paths, start=1):
        try:
            with chunk_path.open("rb") as audio_file:
                kwargs = {
                    "model": model,
                    "file": audio_file,
                }
                if language:
                    kwargs["language"] = language
                if prompt:
                    kwargs["prompt"] = prompt

                response = client.audio.transcriptions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            fail(f"transcription failed on chunk {index}: {exc}")

        text = getattr(response, "text", None)
        if text is None and hasattr(response, "model_dump"):
            text = response.model_dump().get("text")
        if not text:
            fail(f"transcription returned no text for chunk {index}")

        transcripts.append(text.strip())

    return "\n\n".join(part for part in transcripts if part)


# -- output --

def format_duration(duration_seconds: float | None) -> str | None:
    if duration_seconds is None:
        return None

    rounded = int(round(duration_seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def build_markdown(
    media_path: Path,
    transcript_text: str,
    model: str,
    language: str | None,
    chunk_count: int,
    duration_seconds: float | None,
    local: bool,
    segments: list[str] | None = None,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    duration_text = format_duration(duration_seconds)
    backend = "local-whisper" if local else "openai-api"

    frontmatter = [
        "---",
        f'source_media: "{media_path}"',
        f'generated_at: "{generated_at}"',
        f'transcription_model: "{model}"',
        f'transcription_backend: "{backend}"',
        f"chunk_count: {chunk_count}",
    ]
    if language:
        frontmatter.append(f'language_hint: "{language}"')
    if duration_text:
        frontmatter.append(f'duration: "{duration_text}"')
    frontmatter.append("---")

    body = [
        f"# transcript: {media_path.stem}",
        "",
        f"source media: `{media_path}`",
        f"generated at: `{generated_at}`",
        f"model: `{model}` ({backend})",
        f"chunks: `{chunk_count}`",
    ]
    if language:
        body.append(f"language hint: `{language}`")
    if duration_text:
        body.append(f"duration: `{duration_text}`")

    body.extend(
        [
            "",
            "## transcript",
            "",
            transcript_text.strip(),
            "",
        ]
    )

    if segments:
        body.extend(["## segments", "", *segments, ""])

    return "\n".join(frontmatter + [""] + body)


def main() -> None:
    args = parse_args()
    media_path = Path(args.media_path).expanduser().resolve()
    if not media_path.exists():
        fail(f"media path does not exist: {media_path}")

    workspace_root = resolve_workspace_root(Path(__file__).resolve())
    output_path = resolve_output_path(args.output, media_path, workspace_root)
    duration_seconds = get_media_duration_seconds(media_path)

    if args.local:
        model_name = args.model if args.model != DEFAULT_MODEL else DEFAULT_LOCAL_MODEL
        transcript_text, segment_lines = transcribe_local(
            media_path=media_path,
            model_name=model_name,
            language=args.language,
        )
        chunk_count = 1
    else:
        with tempfile.TemporaryDirectory(prefix="speech-transcribe-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            chunk_paths = extract_audio_chunks(media_path, temp_dir)
            transcript_text = transcribe_chunks(
                chunk_paths=chunk_paths,
                model=args.model,
                language=args.language,
                prompt=args.prompt,
            )
        chunk_count = len(chunk_paths)
        segment_lines = []
        if args.segments:
            print("note: --segments is local-only, skipping for the cloud backend", file=sys.stderr)

    model_label = (args.model if args.model != DEFAULT_MODEL else DEFAULT_LOCAL_MODEL) if args.local else args.model

    markdown = build_markdown(
        media_path=media_path,
        transcript_text=transcript_text,
        model=model_label,
        language=args.language,
        chunk_count=chunk_count,
        duration_seconds=duration_seconds,
        local=args.local,
        segments=segment_lines if args.segments else None,
    )
    output_path.write_text(markdown, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
