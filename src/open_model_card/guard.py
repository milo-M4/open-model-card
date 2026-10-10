"""Pre-test state check.

In v1.0 the UI handles the "another model is loaded" case by ASKING the
operator before unloading. This module just answers the question
"what's loaded?" so the UI can phrase the question correctly.

`is_model_loaded` — true when the named model is in `loaded` or
`loading` state on the engine.

`find_loaded_model` — name of the first loaded model on the engine, or
None if no models are loaded.

The legacy `find_block` and `block_reason` functions are kept for
backward compatibility with any callers that import them.
"""

from __future__ import annotations

from urllib.parse import urlparse

from open_model_card.client import EndpointError, model_rows
from open_model_card.engines import REGISTRY
from open_model_card.hostmem import rss_mb_for_port

LARGE_RSS_MB = 8000
WATCH_PORTS = (18434, 8000, 11434)


def is_model_loaded(family: str, url: str, model_id: str, key: str | None, timeout: float = 5.0) -> bool:
    adapter = REGISTRY.get(family)
    if adapter is None:
        return False
    try:
        return bool(adapter.is_loaded(url, model_id, key, timeout))
    except Exception:
        return False


def find_loaded_model(family: str, url: str, key: str | None, timeout: float = 5.0) -> str | None:
    """Return the id of the first loaded model on the engine, or None."""
    adapter = REGISTRY.get(family)
    if adapter is None:
        return None
    try:
        for m in adapter.list_models(url, key, timeout):
            if m.state in ("loaded", "loading"):
                return m.id
    except Exception:
        return None
    return None


# Legacy API — kept for callers that haven't migrated yet.

def _port(base_url: str) -> int | None:
    return urlparse(base_url).port


def block_reason(residents: list[dict], target_base: str, selected: str) -> str | None:
    """residents items: where, model. Same model on the target server is allowed."""
    blocking = []
    target_port = _port(target_base)
    for item in residents:
        same_server = _port(item.get("where") or "") == target_port
        same_model = item.get("model") == selected and selected
        if same_server and same_model:
            continue
        blocking.append(item)
    if not blocking:
        return None
    names = "; ".join(f"{item.get('model') or 'a model'} at {item.get('where')}" for item in blocking)
    return (
        "A model is still loaded (" + names + "). "
        "This run was not started. Unload it or wait, then try again."
    )


def find_block(base_url: str, selected: str, api_key: str) -> str | None:
    residents: list[dict] = []
    ports = {port for port in WATCH_PORTS}
    target_port = _port(base_url)
    if target_port:
        ports.add(target_port)
    for port in sorted(ports):
        where = f"http://127.0.0.1:{port}/v1"
        key = api_key if port == target_port else ""
        try:
            for row in model_rows(where, key, 8):
                state = str(((row.get("status") or {}).get("value")) or "").lower()
                if state in ("loaded", "loading"):
                    residents.append({"where": where, "model": row.get("id") or "unknown"})
        except EndpointError:
            memory = rss_mb_for_port(port)
            if memory.get("available") and (memory.get("rss_mb") or 0) >= LARGE_RSS_MB:
                residents.append({"where": where, "model": "a large model"})
    return block_reason(residents, base_url, selected)
