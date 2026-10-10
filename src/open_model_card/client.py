"""Talk to an OpenAI-compatible /v1/chat/completions endpoint. Stdlib only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class EndpointError(RuntimeError):
    pass


def _request(url: str, payload: dict | None, api_key: str, timeout: float, method: str = "GET") -> tuple[int, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise EndpointError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise EndpointError(f"could not reach {url}: {exc.reason}") from exc


def server_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def unload_model(base_url: str, model: str, api_key: str, timeout: float = 60) -> dict:
    """Ask a llama.cpp router to free the model. Other servers may refuse. Never raises."""
    url = server_root(base_url) + "/models/unload"
    try:
        status, _raw = _request(url, {"model": model}, api_key, timeout, method="POST")
    except EndpointError as exc:
        return {"attempted": True, "unloaded": False, "detail": str(exc)[:180]}
    return {"attempted": True, "unloaded": status == 200, "detail": f"HTTP {status}"}


def model_rows(base_url: str, api_key: str, timeout: float) -> list[dict]:
    status, raw = _request(base_url.rstrip("/") + "/models", None, api_key, timeout)
    if status != 200:
        raise EndpointError(f"models endpoint returned {status}")
    body = json.loads(raw.decode())
    return [item for item in body.get("data", []) if isinstance(item, dict)]


def list_models(base_url: str, api_key: str, timeout: float) -> list[str]:
    return [item.get("id", "") for item in model_rows(base_url, api_key, timeout) if item.get("id")]


def complete(base_url: str, model: str, prompt: str, api_key: str, timeout: float, max_tokens: int = 200) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    started = time.perf_counter()
    status, raw = _request(
        base_url.rstrip("/") + "/chat/completions",
        payload,
        api_key,
        timeout,
        method="POST",
    )
    elapsed = time.perf_counter() - started
    if status != 200:
        raise EndpointError(f"completion returned {status}")
    body = json.loads(raw.decode())
    text = ""
    choices = body.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        # For thinking models, combine content and reasoning_content
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        text = content + "\n" + reasoning if reasoning else content
    usage = body.get("usage") or {}
    return {"text": text, "elapsed_s": round(elapsed, 3), "usage": usage}


def stream_speed(base_url: str, model: str, api_key: str, timeout: float, max_tokens: int = 64) -> dict[str, Any]:
    """Short-prompt speed. This is not an 8k-prefill number."""
    prompt = "Count from 1 to 20. One number per line. No other words."
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    started = time.perf_counter()
    first_any = None
    first_content = None
    parts: list[str] = []
    usage: dict = {}
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise EndpointError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise EndpointError(f"could not reach {url}: {exc.reason}") from exc
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            blob = line[5:].strip()
            if blob == "[DONE]":
                break
            if first_any is None:
                first_any = time.perf_counter()
            try:
                event = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if event.get("usage"):
                usage = event["usage"]
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = (choices[0].get("delta") or {})
            # For thinking models, combine content and reasoning_content
            piece = (delta.get("content") or "") + (delta.get("reasoning_content") or "")
            if piece and first_content is None:
                first_content = time.perf_counter()
            if piece:
                parts.append(piece)
    finished = time.perf_counter()
    text = "".join(parts)
    completion_tokens = usage.get("completion_tokens")
    if not completion_tokens:
        completion_tokens = len(text.split())
    gen_start = first_content or first_any or started
    gen_s = max(finished - gen_start, 1e-6)
    return {
        "prompt": "short count 1 to 20",
        "ttfr_s": None if first_any is None else round(first_any - started, 3),
        "ttft_s": None if first_content is None else round(first_content - started, 3),
        "wall_s": round(finished - started, 3),
        "completion_tokens": completion_tokens,
        "tok_per_s": round(completion_tokens / gen_s, 2),
        "text_preview": text.strip()[:200],
        "note": "Short prompt. Not a long-context prefill measurement.",
    }
