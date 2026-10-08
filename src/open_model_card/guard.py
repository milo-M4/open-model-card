"""Stop a new test while a model is still resident."""

from __future__ import annotations

from urllib.parse import urlparse

from open_model_card.client import EndpointError, model_rows
from open_model_card.hostmem import rss_mb_for_port

LARGE_RSS_MB = 8000
WATCH_PORTS = (18434, 8000, 11434)


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
