"""Per-model RAM cost prediction (hybrid).

Order of preference:

1. Engine API — ask the engine for the actual size. llama.cpp does
   this via /props; Ollama via /api/show. Most reliable when the
   model is loaded.

2. File-size heuristic — find the model file on disk and use
   file_size × 1.2 ≈ resident RSS. This is rough but works when
   the model is on disk but not yet loaded. It does not work for
   Ollama, which stores models in a content-addressed blob store
   and exposes a manifest at /api/show.

3. Refuse — if neither works, the caller should tell the user
   "this engine doesn't tell us the size — pick a model you know
   fits."
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from open_model_card.engines import REGISTRY


# Per-engine model file search paths. Used by the file-size heuristic.
MODEL_SEARCH_ROOTS: dict[str, list[Path]] = {
    "llamacpp": [
        Path.home() / ".hermes" / "models",
        Path.home() / "models",
    ],
    "ollama": [],   # Ollama uses a content-addressed blob store
    "omlx": [
        Path.home() / ".omlx" / "models",
    ],
    "lmstudio": [
        Path.home() / ".cache" / "lm-studio" / "models",
    ],
}

MODEL_EXTENSIONS = {".gguf", ".bin", ".safetensors"}

# Skim these subdirs to keep the scan fast on large models.
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}


@dataclass
class Prediction:
    """The result of a RAM-cost prediction."""

    model_id: str
    family: str
    bytes_predicted: int | None
    source: str            # "engine-api" / "file-size" / "none"
    detail: str = ""


def predict(model_id: str, family: str, url: str, key: str | None) -> Prediction:
    """Predict the RAM cost of loading `model_id` on the engine at `url`."""
    # 1. Engine API
    adapter = REGISTRY.get(family)
    detail = ""
    if adapter is not None and hasattr(adapter, "model_size"):
        try:
            n = adapter.model_size(url, model_id, key)
        except Exception as exc:
            n = None
            detail = f"engine API error: {exc}"
        if n and n > 0:
            return Prediction(model_id=model_id, family=family, bytes_predicted=n, source="engine-api", detail=detail)

    # 2. File-size heuristic
    bytes_predicted, file_detail = _file_size_heuristic(model_id, family)
    if bytes_predicted:
        return Prediction(
            model_id=model_id, family=family,
            bytes_predicted=bytes_predicted, source="file-size", detail=file_detail,
        )

    return Prediction(
        model_id=model_id, family=family,
        bytes_predicted=None, source="none",
        detail=detail or "no engine size; no model file found",
    )


def _file_size_heuristic(model_id: str, family: str) -> tuple[int | None, str]:
    """Find a model file matching `model_id` under the engine's known roots.

    Returns (file_size × 1.2, search_detail).
    """
    roots = MODEL_SEARCH_ROOTS.get(family, [])
    if not roots:
        return None, f"no search roots for {family}"
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.suffix.lower() not in MODEL_EXTENSIONS:
                continue
            # Match the model id loosely: lowercased, ignoring - and _ and case.
            stem = re.sub(r"[-_]", "", path.stem.lower())
            target = re.sub(r"[-_]", "", model_id.lower())
            if stem == target or target in stem or stem in target:
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                predicted = int(size * 1.2)
                return predicted, f"file {path} ({size} bytes) × 1.2"
    return None, "no matching model file found"


def fits(predicted_bytes: int | None, free_mb: float | None, headroom_mb: float = 4096) -> dict:
    """Decide whether a test should be allowed to run.

    Returns a dict {ok, reason, predicted_mb, headroom_mb}.
    """
    if predicted_bytes is None:
        return {"ok": False, "reason": "don't know the size; cannot decide", "predicted_mb": None, "headroom_mb": headroom_mb}
    if free_mb is None:
        return {"ok": False, "reason": "don't know free RAM; cannot decide", "predicted_mb": round(predicted_bytes / 1048576, 1), "headroom_mb": headroom_mb}
    predicted_mb = predicted_bytes / 1048576
    required = predicted_mb + headroom_mb
    if free_mb < required:
        gap = required - free_mb
        return {"ok": False, "reason": f"need {required:.0f} MB free, have {free_mb:.0f} MB (short {gap:.0f} MB)", "predicted_mb": round(predicted_mb, 1), "headroom_mb": headroom_mb}
    spare = free_mb - required
    verdict = "ok" if spare > 4096 else "tight"
    return {"ok": True, "reason": verdict, "predicted_mb": round(predicted_mb, 1), "headroom_mb": headroom_mb, "spare_mb": round(spare, 1)}
