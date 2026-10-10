#!/usr/bin/env python3
"""Test the open-model-card UI server end-to-end."""
import sys
import os
import subprocess
import time
import json
import signal
from pathlib import Path

sys.path.insert(0, "/Users/milo/Milo-Workspace/code/open-model-card/src")

from open_model_card.ui import serve
from pathlib import Path

def main():
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("=== Starting UI server on port 8765 ===", flush=True)
    
    # Start server in a subprocess so we can test it
    import threading
    
    # Run server in background thread
    server_thread = threading.Thread(
        target=serve,
        args=(out_dir, 8765),
        daemon=True,
    )
    server_thread.start()
    
    # Wait for server to be ready
    time.sleep(2)
    
    import urllib.request
    import urllib.error
    
    results = {}
    
    # Test 1: UI page
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8765/")
        html = resp.read().decode()
        results["ui_page"] = {
            "status": resp.status,
            "length": len(html),
            "has_open_model_card": "OPEN MODEL CARD" in html,
            "has_hermes_key_button": "hermeskey" in html,
            "has_pause_checkbox": "paused" in html,
            "has_scan_button": "scan" in html,
            "has_list_button": "list" in html,
            "has_run_button": "run" in html,
            "data_url_buttons": "data-url" in html,
        }
        print("Test 1 - UI page:", "PASS" if results["ui_page"]["has_open_model_card"] else "FAIL", flush=True)
    except Exception as e:
        results["ui_page"] = {"error": str(e)}
        print("Test 1 - UI page: FAIL -", e, flush=True)
    
    # Test 2: /api/scan (POST, not GET)
    try:
        req = urllib.request.Request("http://127.0.0.1:8765/api/scan", data=b'{}', headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read().decode())
        results["api_scan"] = {
            "status": resp.status,
            "file_count": len(data.get("files", [])),
            "files": data.get("files", []),
        }
        print(f"Test 2 - /api/scan: PASS (found {results['api_scan']['file_count']} files)", flush=True)
    except Exception as e:
        results["api_scan"] = {"error": str(e)}
        print("Test 2 - /api/scan: FAIL -", e, flush=True)
    
    # Test 3: /api/models (no key - should fail on Hermes)
    try:
        payload = json.dumps({
            "base_url": "http://127.0.0.1:18434/v1",
            "api_key": "",
            "model": "",
            "use_hermes_key": False,
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/models",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read().decode())
        results["api_models_no_key"] = {
            "status": resp.status,
            "models": data.get("models", []),
            "error": data.get("error", None),
        }
        print(f"Test 3 - /api/models (no key): {resp.status}", flush=True)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        results["api_models_no_key"] = {
            "status": e.code,
            "error": body[:200],
        }
        print(f"Test 3 - /api/models (no key): FAIL with HTTP {e.code}", flush=True)
    except Exception as e:
        results["api_models_no_key"] = {"error": str(e)}
        print("Test 3 - /api/models (no key): FAIL -", e, flush=True)
    
    # Test 4: /api/models (with Hermes key)
    try:
        # First check the server.json
        server_json_path = Path.home() / ".hermes" / "runtimes" / "llamacpp" / "server.json"
        if server_json_path.is_file():
            with open(server_json_path) as f:
                server_config = json.load(f)
            hermes_key = server_config.get("api_key", "")
            print(f"  [info] server.json key exists: {bool(hermes_key)}", flush=True)
            print(f"  [info] server.json base_url: {server_config.get('base_url')}", flush=True)
        else:
            hermes_key = ""
            print("  [info] No server.json found", flush=True)
        
        payload = json.dumps({
            "base_url": "http://127.0.0.1:18434/v1",
            "model": "",
            "use_hermes_key": True,
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/models",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read().decode())
        results["api_models_hermes_key"] = {
            "status": resp.status,
            "models": data.get("models", []),
            "error": data.get("error", None),
        }
        print(f"Test 4 - /api/models (Hermes key): PASS (found {len(data.get('models', []))} models)", flush=True)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        results["api_models_hermes_key"] = {
            "status": e.code,
            "error": body[:200],
        }
        print(f"Test 4 - /api/models (Hermes key): FAIL with HTTP {e.code}: {body[:200]}", flush=True)
    except Exception as e:
        results["api_models_hermes_key"] = {"error": str(e)}
        print("Test 4 - /api/models (Hermes key): FAIL -", e, flush=True)
    
    # Test 5: Check Hermes key file
    server_json_path = Path.home() / ".hermes" / "runtimes" / "llamacpp" / "server.json"
    results["key_file"] = {
        "exists": server_json_path.is_file(),
        "has_key": False,
        "base_url": None,
    }
    if server_json_path.is_file():
        with open(server_json_path) as f:
            config = json.load(f)
        results["key_file"]["has_key"] = bool(config.get("api_key"))
        results["key_file"]["base_url"] = config.get("base_url")
    print(f"Test 5 - Key file: exists={results['key_file']['exists']}, has_key={results['key_file']['has_key']}", flush=True)
    
    # Print summary
    print("\n=== SUMMARY ===", flush=True)
    for test_name, result in results.items():
        print(f"\n--- {test_name} ---", flush=True)
        print(json.dumps(result, indent=2), flush=True)
    
    # Return exit code based on actual failures (errors that mean real problems)
    failures = []
    for name, result in results.items():
        if name == "api_models_no_key" and result.get("status") == 400:
            # This is EXPECTED — Hermes requires a key, so no-key returns 400
            # Mark as pass with a note
            print("  (Note: 400 without key is expected — Hermes requires authentication)", flush=True)
        elif "error" in result and result["error"] is not None:
            failures.append(name)
    
    if failures:
        print(f"\nFAILURES: {failures}", flush=True)
        return 1
    else:
        print("\nALL TESTS PASSED", flush=True)
        return 0

if __name__ == "__main__":
    sys.exit(main())
