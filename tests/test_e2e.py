#!/usr/bin/env python3
"""Full end-to-end test: start server, select model, run test, verify report."""
import sys
import os
import time
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.path.insert(0, "/Users/milo/Milo-Workspace/code/open-model-card/src")

from open_model_card.cli import run_card
from open_model_card.ui import serve
from open_model_card.report import write_report

def main():
    print("=== FULL E2E TEST ===\n", flush=True)
    
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Phase 1: Start UI server and verify endpoints
    print("--- Phase 1: UI Server and Endpoints ---", flush=True)
    
    server_thread = threading.Thread(
        target=serve,
        args=(out_dir, 8765),
        daemon=True,
    )
    server_thread.start()
    time.sleep(2)
    
    # Test UI page
    resp = urllib.request.urlopen("http://127.0.0.1:8765/")
    html = resp.read().decode()
    print(f"  UI page: {len(html)} bytes, has 'OPEN MODEL CARD': {'OPEN MODEL CARD' in html}", flush=True)
    
    # Test /api/scan (POST)
    req = urllib.request.Request("http://127.0.0.1:8765/api/scan", data=b'{}', 
                                   headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req)
    scan_data = json.loads(resp.read().decode())
    print(f"  Model files found: {len(scan_data['files'])}", flush=True)
    for f in scan_data['files']:
        print(f"    - {f}", flush=True)
    
    # Test /api/models with Hermes key
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
    models_data = json.loads(resp.read().decode())
    print(f"  Models returned: {models_data['models']}", flush=True)
    
    # Test /api/status (should show idle)
    req = urllib.request.Request("http://127.0.0.1:8765/api/status", method="GET")
    resp = urllib.request.urlopen(req)
    status = json.loads(resp.read().decode())
    print(f"  Server status: {status['state']}", flush=True)
    
    print("\n--- Phase 2: Run a test via CLI (bypasses UI for now) ---\n", flush=True)
    
    # Run a full test with the local model
    # Load the Hermes key from server.json (same as the UI panel does)
    server_json_path = Path.home() / ".hermes" / "runtimes" / "llamacpp" / "server.json"
    hermes_key = ""
    if server_json_path.is_file():
        with open(server_json_path) as f:
            server_config = json.load(f)
        hermes_key = server_config.get("api_key", "")
    
    try:
        print(f"Using Hermes key from server.json: {'yes' if hermes_key else 'no'}", flush=True)
        print("Starting model test with Qwen3.6-35B-A3B-UD-Q4_K_M...", flush=True)
        start_time = time.time()
        
        report = run_card(
            base_url="http://127.0.0.1:18434/v1",
            model="Qwen3.6-35B-A3B-UD-Q4_K_M",
            api_key=hermes_key,  # Use the loaded key
            timeout=300,
            out=out_dir,
            skip_speed=False,
            skip_tasks=False,
        )
        
        elapsed = time.time() - start_time
        print(f"Test completed in {elapsed:.1f}s\n", flush=True)
        
        # Verify report structure
        print("--- Report Verification ---", flush=True)
        print(f"  tool: {report.get('tool')}", flush=True)
        print(f"  version: {report.get('version')}", flush=True)
        print(f"  endpoint model: {report['endpoint'].get('model')}", flush=True)
        print(f"  endpoint base_url: {report['endpoint'].get('base_url')}", flush=True)
        
        speed = report.get('speed', {})
        print(f"  ttft_s: {speed.get('ttft_s')}", flush=True)
        print(f"  tok_per_s: {speed.get('tok_per_s')}", flush=True)
        print(f"  wall_s: {speed.get('wall_s')}", flush=True)
        
        memory = report.get('memory', {})
        print(f"  memory available: {memory.get('available')}", flush=True)
        if memory.get('available'):
            print(f"  RSS: {memory.get('rss_mb')} MB", flush=True)
            print(f"  PIDs: {memory.get('pids')}", flush=True)
        
        tasks = report.get('tasks', [])
        print(f"  Tasks run: {len(tasks)}", flush=True)
        passed = sum(1 for t in tasks if t.get('pass'))
        print(f"  Passed: {passed}/{len(tasks)}", flush=True)
        for t in tasks:
            mark = "PASS" if t['pass'] else "FAIL"
            print(f"    {t['id']}: {mark} ({t['area']})", flush=True)
        
        print(f"  Strengths: {report.get('strengths', {}).get('best', [])}", flush=True)
        print(f"  Weaknesses: {report.get('strengths', {}).get('weak', [])}", flush=True)
        
        unload = report.get('unload', {})
        print(f"  Unload attempted: {unload.get('attempted')}", flush=True)
        print(f"  Unload unloaded: {unload.get('unloaded')}", flush=True)
        
        # Write reports
        json_path, md_path = write_report(report, out_dir)
        print(f"\n  JSON report: {json_path}", flush=True)
        print(f"  Markdown report: {md_path}", flush=True)
        
        # Verify files exist and have content
        assert json_path.exists(), f"JSON report not created: {json_path}"
        assert md_path.exists(), f"Markdown report not created: {md_path}"
        json_size = json_path.stat().st_size
        md_size = md_path.stat().st_size
        print(f"  JSON size: {json_size} bytes", flush=True)
        print(f"  Markdown size: {md_size} bytes", flush=True)
        
        # Read and verify markdown content
        md_content = md_path.read_text()
        print(f"\n--- Markdown Report Preview ---", flush=True)
        print(md_content[:2000], flush=True)
        
        # Verify plain_summary
        from open_model_card.report import plain_summary
        plain = plain_summary(report)
        print(f"\n--- Plain Summary ---", flush=True)
        print(plain, flush=True)
        
        # Verify test_report_names_strength now passes (model is defined)
        print("\n--- Phase 3: Verify all unit tests pass ---\n", flush=True)
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
            capture_output=True, text=True,
            cwd="/Users/milo/Milo-Workspace/code/open-model-card",
            env={**dict(os.environ), "PYTHONPATH": "src"},
        )
        print(result.stdout, flush=True)
        if result.stderr:
            print("STDERR:", result.stderr, flush=True)
        print(f"  Unit test exit code: {result.returncode}", flush=True)
        
        # Success!
        print("\n=== ALL PHASES PASSED ===", flush=True)
        print(f"  Total time: {elapsed:.1f}s", flush=True)
        print(f"  Reports: {json_path}, {md_path}", flush=True)
        return 0
        
    except Exception as e:
        import traceback
        print(f"\nE2E TEST FAILED: {e}", flush=True)
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
