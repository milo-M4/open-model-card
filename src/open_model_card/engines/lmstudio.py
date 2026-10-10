"""LM Studio adapter.

LM Studio serves an OpenAI-compatible /v1/models endpoint on the user-
configured port (default 1234). It does NOT expose an unload API — the
user must unload the model from the LM Studio UI.
"""

from __future__ import annotations

import json

from open_model_card.engines import EngineAdapter, ModelInfo, ProbeResult, UnloadResult
from open_model_card.client import _request


class LMStudioAdapter(EngineAdapter):
    name = "LM Studio"
    family = "lmstudio"

    def probe(self, url: str, key: str | None, timeout: float = 5.0) -> ProbeResult:
        try:
            status, _ = _request(url.rstrip("/") + "/models", None, key or "", timeout)
        except Exception as exc:
            return ProbeResult(reachable=False, detail=str(exc)[:120])
        if status != 200:
            return ProbeResult(reachable=False, detail=f"HTTP {status}")
        return ProbeResult(reachable=True, needs_auth=False)

    def list_models(self, url: str, key: str | None, timeout: float = 15.0) -> list[ModelInfo]:
        try:
            status, raw = _request(url.rstrip("/") + "/models", None, key or "", timeout)
        except Exception:
            return []
        if status != 200:
            return []
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

    def model_size(self, url: str, model_id: str, key: str | None, timeout: float = 10.0) -> int | None:
        # LM Studio doesn't expose size. The caller falls back to file-size heuristic.
        return None

    def unload(self, url: str, model_id: str, key: str | None, timeout: float = 60.0) -> UnloadResult:
        return UnloadResult(attempted=False, unloaded=False, detail="unload in the LM Studio UI")
