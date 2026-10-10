import threading
import unittest
import urllib.request

from open_model_card.ui import PAGE, Handler


class UiTests(unittest.TestCase):
    def test_panel_has_three_regions(self):
        # v1.0 uses region labels, not "Step 1/2/3" headings.
        self.assertIn("SYSTEM", PAGE)
        self.assertIn("WHAT TO DO", PAGE)
        self.assertIn("RESULTS", PAGE)

    def test_panel_uses_plain_language(self):
        # No terminal jargon the non-technical user won't understand.
        self.assertNotIn("sudo", PAGE)
        self.assertNotIn("--base-url", PAGE)
        # The thinking toggle is on the page.
        self.assertIn("reasoning trace", PAGE)
        # The schema version is in the footer.
        self.assertIn("Schema v1.0", PAGE)

    def test_page_serves_locally(self):
        from http.server import ThreadingHTTPServer

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
                body = resp.read().decode()
            self.assertEqual(resp.status, 200)
            self.assertIn("OPEN MODEL CARD", body)
            self.assertIn("SYSTEM", body)
        finally:
            server.shutdown()
            server.server_close()

    def test_page_javascript_parses(self):
        """Regression: a bug introduced literal newlines inside a JS string in
        the PAGE constant, breaking the entire UI. This test loads the page
        and checks that the embedded JS has no obvious syntax errors (no
        unterminated string literals)."""
        import re
        m = re.search(r"<script>([\s\S]*?)</script>", PAGE)
        self.assertIsNotNone(m, "page must have a script tag")
        script = m.group(1)
        # Check each line for an odd number of unescaped quotes — that
        # would mean a string literal is unterminated.
        lines = script.split("\n")
        broken = []
        for i, line in enumerate(lines, 1):
            count = 0
            j = 0
            while j < len(line):
                if line[j] == "\\" and j + 1 < len(line):
                    j += 2
                    continue
                if line[j] == '"':
                    count += 1
                j += 1
            if count % 2 == 1:
                broken.append((i, line))
        self.assertEqual(broken, [], f"unterminated JS strings: {broken[:3]}")

    def test_state_endpoint_via_get(self):
        """v1.0 fix: /api/state must work with GET (the page uses GET)."""
        from http.server import ThreadingHTTPServer

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                import json
                body = json.loads(resp.read().decode())
                self.assertIn("machine", body)
                self.assertIn("engines", body)
        finally:
            server.shutdown()
            server.server_close()

    def test_state_endpoint_via_post(self):
        """v1.0 fix: /api/state must also accept POST (some clients use it)."""
        from http.server import ThreadingHTTPServer
        import json

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/state",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode())
                self.assertIn("machine", body)
        finally:
            server.shutdown()
            server.server_close()

    def test_stale_running_state_is_corrected(self):
        """If JOB.state is 'running' but the worker thread is dead, /api/status
        should mark it as 'error' so the UI doesn't sit on a stale banner."""
        from http.server import ThreadingHTTPServer
        import json
        import open_model_card.ui as ui_mod

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # Force a stale "running" state with a dead thread.
            class _Dead:
                def is_alive(self): return False
            with ui_mod.JOB_LOCK:
                ui_mod.JOB["state"] = "running"
                ui_mod.JOB["thread"] = _Dead()
                ui_mod.JOB["error"] = ""
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as resp:
                body = json.loads(resp.read().decode())
            self.assertEqual(body["state"], "error")
            self.assertIn("interrupted", body.get("error", ""))
            # Reset for any subsequent tests.
            with ui_mod.JOB_LOCK:
                ui_mod.JOB["state"] = "idle"
                ui_mod.JOB["thread"] = None
                ui_mod.JOB["error"] = ""
        finally:
            server.shutdown()
            server.server_close()
