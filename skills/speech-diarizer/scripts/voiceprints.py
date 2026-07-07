"""shared voiceprint store + matching for speech-diarizer.

a "voiceprint" is the per-speaker embedding pyannote already produces during
diarization. this module persists named voiceprints and matches new speaker
embeddings against them by cosine similarity. no model/training - just storage
and nearest-neighbour lookup.

the store is machine-global so every copy of the scripts shares one set of
voiceprints. location resolves in this order:
    1. an explicit path passed in (the --store flag)
    2. $SPEECH_DIARIZER_VOICEPRINTS
    3. ~/.config/speech-diarizer/voiceprints.json  (default)

set $SPEECH_DIARIZER_VOICEPRINTS to an iCloud/synced path for cross-machine use.

store schema:
    {
      "version": 1,
      "model": "pyannote/speaker-diarization-3.1",   # embeddings only compare within one model
      "speakers": {
        "Rami": {"embeddings": [[...], ...], "samples": ["call.m4a#SPEAKER_01", ...]}
      }
    }
"""

import json
import os
from pathlib import Path

import numpy as np

DEFAULT_STORE = Path.home() / ".config" / "speech-diarizer" / "voiceprints.json"
CACHE_DIR = Path.home() / ".cache" / "speech-diarizer"


def cache_dir() -> Path:
    """where diarize.py stashes per-run embeddings for later enrollment."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def store_path(explicit: str | None = None) -> Path:
    """resolve the store location: explicit arg > env var > ~/.config default."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("SPEECH_DIARIZER_VOICEPRINTS")
    if env:
        return Path(env).expanduser()
    return DEFAULT_STORE


def load_store(path: str | None = None) -> dict:
    p = store_path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": 1, "model": None, "speakers": {}}


def save_store(store: dict, path: str | None = None) -> None:
    p = store_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def _norm(v) -> "np.ndarray":
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n else v


def centroid(embeddings: list) -> "np.ndarray":
    """unit-norm average of a speaker's enrolled embeddings."""
    stacked = np.stack([_norm(e) for e in embeddings])
    return _norm(stacked.mean(axis=0))


def cosine(a, b) -> float:
    return float(np.dot(_norm(a), _norm(b)))


def identify(speaker_embeddings: dict, store: dict, threshold: float) -> dict:
    """match each SPEAKER_XX embedding to the closest enrolled name.

    returns {SPEAKER_XX: {"name": str|None, "similarity": float, "scores": [(sim, name), ...]}}
    name is None when the best match is below threshold.
    """
    names = list(store["speakers"].keys())
    centroids = {n: centroid(store["speakers"][n]["embeddings"]) for n in names}
    results = {}
    for spk, emb in speaker_embeddings.items():
        scores = sorted(((cosine(emb, centroids[n]), n) for n in names), reverse=True)
        best_sim = scores[0][0] if scores else 0.0
        name = scores[0][1] if scores and best_sim >= threshold else None
        results[spk] = {"name": name, "similarity": best_sim, "scores": scores}
    return results


def enroll(name: str, embedding, store: dict, model: str | None, source: str | None = None) -> None:
    """add one embedding sample for `name`. refuses to mix diarization models."""
    if store.get("model") and model and store["model"] != model:
        raise ValueError(
            f"store was built with '{store['model']}' but this sample came from '{model}'. "
            "embeddings from different diarization models are not comparable. either re-run "
            "with the store's model, or start a fresh store."
        )
    if model and not store.get("model"):
        store["model"] = model
    sp = store["speakers"].setdefault(name, {"embeddings": [], "samples": []})
    sp["embeddings"].append([float(x) for x in embedding])
    if source:
        sp["samples"].append(source)
