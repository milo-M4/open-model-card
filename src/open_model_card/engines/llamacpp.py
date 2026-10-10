"""llama.cpp adapter (Hermes llama.cpp + standalone llama-server).

The Hermes variant reads the API key from
~/.hermes/runtimes/llamacpp/server.json so the operator never has to
paste it. Standalone llama-server takes a key in the URL or as
Authorization header.

Endpoints:
  GET  /v1/models         — list models (OpenAI-compatible)
  GET  /props             — runtime + model info (llama.cpp extension)
  POST /models/unload     — release a loaded model
"""

from __future__ import annotations

import json
from pathlib import Path

from open_model_card.engines import EngineAdapter, ModelInfo, ProbeResult, UnloadResult
from open_model_card.client import _request


def _hermes_key() -> str | None:
    """Read the API key Hermes wrote for the llama.cpp server."""
    p = Path.home() / ".hermes" / "runtimes" / "llamacpp" / "server.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("api_key") or None
    except (json.JSONDecodeError, OSError):
        return None


class LlamaCppAdapter(EngineAdapter):
    name = "llama.cpp"
    family = "llamacpp"

    def probe(self, url: str, key: str | None, timeout: float = 5.0) -> ProbeResult:
        # /v1/models is OpenAI-compatible; Hermes and standalone both serve it.
        try:
            status, raw = _request(url.rstrip("/") + "/models", None, key or "", timeout)
        except Exception as exc:
            return ProbeResult(reachable=False, detail=str(exc)[:120])

        if status == 401:
            # The server is up but wants auth. Return needs_auth so the
            # UI can offer "load key from server.json" or ask the user.
            return ProbeResult(reachable=True, needs_auth=True, detail="401: API key required")
        if status != 200:
            return ProbeResult(reachable=False, detail=f"HTTP {status}")

        version = None
        try:
            status2, raw2 = _request(url.rstrip("/").removesuffix("/v1") + "/props", None, key or "", timeout)
            if status2 == 200:
                body = json.loads(raw2.decode())
                version = body.get("build_info") or body.get("version")
        except Exception:
            pass

        return ProbeResult(reachable=True, needs_auth=False, version=version)

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
            state = (item.get("status") or {}).get("value") if isinstance(item.get("status"), dict) else None
            out.append(ModelInfo(id=mid, state=state, extra=item))
        return out

    def model_size(self, url: str, model_id: str, key: str | None, timeout: float = 10.0) -> int | None:
        try:
            status, raw = _request(url.rstrip("/").removesuffix("/v1") + "/props", None, key or "", timeout)
        except Exception:
            return None
        if status != 200:
            return None
        try:
            body = json.loads(raw.decode())
        except json.JSONDecodeError:
            return None
        # /props returns model info under various keys across llama.cpp versions.
        # Look for size in bytes, or fall back to n_params * 2 (fp16 bytes).
        for key_name in ("model_size_bytes", "size_bytes"):
            if body.get(key_name):
                return int(body[key_name])
        n_params = body.get("n_params")
        if isinstance(n_params, (int, float)) and n_params > 0:
            # bytes ≈ params × bytes-per-param. fp16 = 2, q4 ≈ 0.6. Default to fp16 if unknown.
            return int(n_params * 2)
        return None

    def unload(self, url: str, model_id: str, key: str | None, timeout: float = 60.0) -> UnloadResult:
        # POST /models/unload — server-root URL, not /v1.
        server_root = url.rstrip("/")
        if server_root.endswith("/v1"):
            server_root = server_root[:-3]
        try:
            status, _raw = _request(server_root + "/models/unload", {"model": model_id}, key or "", timeout, method="POST")
        except Exception as exc:
            return UnloadResult(attempted=True, unloaded=False, detail=str(exc)[:180])
        return UnloadResult(attempted=True, unloaded=(status == 200), detail=f"HTTP {status}")

    def is_loaded(self, url: str, model_id: str, key: str | None, timeout: float = 5.0) -> bool:
        for m in self.list_models(url, key, timeout):
            if m.id == model_id and m.state in ("loaded", "loading"):
                return True
        return False

    @staticmethod
    def hermes_key() -> str | None:
        return _hermes_key()
