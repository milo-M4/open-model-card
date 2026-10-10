#!/usr/bin/env python3
"""Live UI server smoke test against a real model on port 18434.

Verifies every POST endpoint behaves as documented. Uses the Hermes key
already saved at ~/.hermes/runtimes/llamacpp/server.json so it does not
need the user to paste a password.
"""
import sys
import json
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, "/Users/milo/Milo-Workspace/code/open-model-card/src")

from open_model_card.ui import serve


def post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def main():
    out_dir = Path("/tmp/omc-ui-smoke/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    server_thread = threading.Thread(target=serve, args=(out_dir, 8770), daemon=True)
    server_thread.start()
    time.sleep(2)

    print("=== UI smoke test (port 8770) ===", flush=True)

    # 1. UI page
    code, html = get("http://127.0.0.1:8770/")
    assert code == 200, f"UI page code {code}"
    assert "OPEN MODEL CARD" in html
    assert "thinking" in html.lower(), "missing thinking checkbox"
    assert "status-dot" in html, "missing status dots"
    assert "(press the button below to fill from this Mac)" in html, "missing key placeholder"
    assert "showKeyLoaded" in html or "loaded from this Mac" in html, "missing loaded placeholder"
    print(f"[OK] UI page renders, size={len(html)}", flush=True)

    # 2. /api/probe for each preset
    for url, expected in [
        ("http://127.0.0.1:18434/v1", True),
        ("http://127.0.0.1:8000/v1", False),
        ("http://127.0.0.1:11434/v1", False),
    ]:
        code, data = post(
            "http://127.0.0.1:8770/api/probe",
            {"url": url, "use_hermes_key": url.endswith("18434/v1"), "api_key": ""},
        )
        assert code == 200
        actual = data.get("reachable", False)
        ok = actual == expected or (expected is False and not actual)
        print(f"[{'OK' if ok else 'FAIL'}] probe {url}: reachable={actual} detail={data.get('detail', '')[:60]}", flush=True)

    # 3. /api/scan
    code, data = post("http://127.0.0.1:8770/api/scan", {})
    assert code == 200 and data.get("files"), "scan should return files"
    print(f"[OK] /api/scan returned {len(data['files'])} files", flush=True)

    # 4. /api/models with Hermes key
    code, data = post(
        "http://127.0.0.1:8770/api/models",
        {"base_url": "http://127.0.0.1:18434/v1", "use_hermes_key": True, "model": ""},
    )
    assert code == 200 and data.get("models"), f"models failed: {data}"
    print(f"[OK] /api/models returned {data['models']}", flush=True)

    # 5. /api/compare with no saved cards
    code, data = post("http://127.0.0.1:8770/api/compare", {})
    assert code == 400 and "No saved cards" in (data.get("error") or ""), f"compare error: {data}"
    print(f"[OK] /api/compare empty-folder error returned", flush=True)

    # 6. /api/run with paused checkbox (use already-saved card to avoid long run)
    code, data = post(
        "http://127.0.0.1:8770/api/run",
        {"base_url": "http://127.0.0.1:18434/v1", "use_hermes_key": True, "model": "Qwen3.6-35B-A3B-UD-Q4_K_M", "thinking_aware": True},
    )
    assert code == 200 and data.get("started"), f"run failed: {data}"
    print(f"[OK] /api/run started", flush=True)

    # 7. /api/status polls until done or error
    for i in range(40):
        time.sleep(10)
        code, status = get("http://127.0.0.1:8770/api/status")
        status = json.loads(status)
        elapsed = status.get("elapsed_s")
        step = status.get("step")
        state = status.get("state")
        print(f"  poll {i}: state={state} step={step} elapsed={elapsed}s", flush=True)
        if state == "done":
            print(f"[OK] /api/run completed, plain summary length={len(status.get('plain', ''))}", flush=True)
            plain = status.get("plain", "")
            if "thinking" in plain.lower():
                print(f"[OK] plain summary mentions thinking-aware mode", flush=True)
            break
        if state == "error":
            print(f"[FAIL] /api/run error: {status.get('error')}", flush=True)
            return 1
    else:
        print("[FAIL] /api/run timed out", flush=True)
        return 1

    # 8. /api/compare with saved card
    code, data = post("http://127.0.0.1:8770/api/compare", {})
    assert code == 200 and data.get("plain"), f"compare with cards failed: {data}"
    print(f"[OK] /api/compare produced summary, length={len(data['plain'])}", flush=True)
    print(f"  plain preview: {data['plain'][:200]}...", flush=True)

    print("\n=== All UI smoke checks passed ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
