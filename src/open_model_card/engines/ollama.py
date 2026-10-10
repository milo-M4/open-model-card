"""Ollama adapter.

Ollama serves an OpenAI-compatible /v1/models endpoint plus native
endpoints (/api/tags, /api/show, /api/generate). We use:
  GET  /v1/models       — list models
  GET  /api/show        — size, details, format
  POST /api/generate    — unload by sending keep_alive: 0
"""

from __future__ import annotations

import json

from open_model_card.engines import EngineAdapter, ModelInfo, ProbeResult, UnloadResult
from open_model_card.client import _request


def _server_root(url: str) -> str:
    """Strip /v1 from a base URL; Ollama native endpoints live at the root."""
    s = url.rstrip("/")
    if s.endswith("/v1"):
        s = s[:-3]
    return s


class OllamaAdapter(EngineAdapter):
    name = "Ollama"
    family = "ollama"

    def probe(self, url: str, key: str | None, timeout: float = 5.0) -> ProbeResult:
        try:
            status, _ = _request(url.rstrip("/") + "/models", None, key or "", timeout)
        except Exception as exc:
            return ProbeResult(reachable=False, detail=str(exc)[:120])
        if status != 200:
            return ProbeResult(reachable=False, detail=f"HTTP {status}")
        # Version via /api/version (native).
        try:
            status2, raw2 = _request(_server_root(url) + "/api/version", None, key or "", timeout)
            version = json.loads(raw2.decode()).get("version") if status2 == 200 else None
        except Exception:
            version = None
        return ProbeResult(reachable=True, needs_auth=False, version=version)

    def list_models(self, url: str, key: str | None, timeout: float = 15.0) -> list[ModelInfo]:
        try:
            status, raw = _request(_server_root(url) + "/api/tags", None, key or "", timeout)
        except Exception:
            return []
        if status != 200:
            return []
        body = json.loads(raw.decode())
        out: list[ModelInfo] = []
        for item in body.get("models", []) or []:
            if not isinstance(item, dict):
                continue
            mid = item.get("name") or ""
            if not mid:
                continue
            out.append(ModelInfo(id=mid, size_bytes=item.get("size"), extra=item))
        return out

    def model_size(self, url: str, model_id: str, key: str | None, timeout: float = 10.0) -> int | None:
        try:
            status, raw = _request(_server_root(url) + "/api/show", {"name": model_id}, key or "", timeout, method="POST")
        except Exception:
            return None
        if status != 200:
            return None
        try:
            body = json.loads(raw.decode())
        except json.JSONDecodeError:
            return None
        return body.get("size")

    def unload(self, url: str, model_id: str, key: str | None, timeout: float = 60.0) -> UnloadResult:
        # Ollama unloads on next request with keep_alive: 0.
        try:
            status, _raw = _request(
                _server_root(url) + "/api/generate",
                {"model": model_id, "keep_alive": 0},
                key or "",
                timeout,
                method="POST",
            )
        except Exception as exc:
            return UnloadResult(attempted=True, unloaded=False, detail=str(exc)[:180])
        return UnloadResult(attempted=True, unloaded=(status == 200), detail=f"HTTP {status}")

    def is_loaded(self, url: str, model_id: str, key: str | None, timeout: float = 5.0) -> bool:
        try:
            status, raw = _request(_server_root(url) + "/api/ps", None, key or "", timeout)
        except Exception:
            return False
        if status != 200:
            return False
        try:
            body = json.loads(raw.decode())
        except json.JSONDecodeError:
            return False
        for item in body.get("models", []) or []:
            if item.get("name") == model_id:
                return True
        return False
