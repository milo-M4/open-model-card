"""oMLX adapter (Apple MLX framework server).

oMLX is an Apple-Silicon-only model server. It serves an
OpenAI-compatible /v1/models endpoint. Unload semantics are engine-
specific and may require restarting the server.

API key resolution (in order):
  1. The `key` argument passed to the adapter call.
  2. The key in `~/.omlx/settings.json` under `auth.api_key`.
"""

from __future__ import annotations

import json
from pathlib import Path

from open_model_card.engines import EngineAdapter, ModelInfo, ProbeResult, UnloadResult
from open_model_card.client import _request


def _omlx_key() -> str | None:
    """Read the API key oMLX wrote to its settings file."""
    p = Path.home() / ".omlx" / "settings.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    auth = data.get("auth") if isinstance(data, dict) else None
    if not isinstance(auth, dict):
        return None
    key = auth.get("api_key") or ""
    return key or None


class OMLXAdapter(EngineAdapter):
    name = "oMLX"
    family = "omlx"

    def probe(self, url: str, key: str | None, timeout: float = 5.0) -> ProbeResult:
        # oMLX sometimes doesn't have auth.api_key set at all, or
        # has skip_api_key_verification=True. In that case any key (or
        # none) is accepted. Try with the discovered key first; if
        # that fails with 401, retry without a key.
        candidate_keys = []
        if key:
            candidate_keys.append(key)
        if not key or key != _omlx_key():
            discovered = _omlx_key()
            if discovered:
                candidate_keys.append(discovered)
        candidate_keys.append("")  # try with no key as a last resort

        for k in candidate_keys:
            try:
                status, _ = _request(url.rstrip("/") + "/models", None, k, timeout)
            except Exception as exc:
                return ProbeResult(reachable=False, detail=str(exc)[:120])
            if status == 200:
                return ProbeResult(reachable=True, needs_auth=False)
            if status == 401:
                continue
            return ProbeResult(reachable=False, detail=f"HTTP {status}")

        return ProbeResult(reachable=True, needs_auth=True, detail="401: API key required")

    def list_models(self, url: str, key: str | None, timeout: float = 15.0) -> list[ModelInfo]:
        # Same key-fallback logic as probe.
        for k in [key, _omlx_key(), ""]:
            if k is None:
                continue
            try:
                status, raw = _request(url.rstrip("/") + "/models", None, k, timeout)
            except Exception:
                continue
            if status == 200:
                body = json.loads(raw.decode())
                out: list[ModelInfo] = []
                for item in body.get("data", []) or []:
                    if not isinstance(item, dict):
                        continue
                    mid = item.get("id") or ""
                    if not mid:
                        continue
                    out.append(ModelInfo(id=mid, extra=item))
                return out
        return []

    def unload(self, url: str, model_id: str, key: str | None, timeout: float = 60.0) -> UnloadResult:
        # oMLX does not expose a standard unload endpoint. Refuse silently.
        return UnloadResult(attempted=False, unloaded=False, detail="oMLX unload not implemented; restart the server to free memory")

