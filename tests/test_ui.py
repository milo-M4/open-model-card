import threading
import unittest
import urllib.request

from open_model_card.ui import PAGE, Handler


class UiTests(unittest.TestCase):
    def test_panel_is_plain_language(self):
        self.assertIn("STEP 1", PAGE)
        self.assertIn("Where is the model running?", PAGE)
        self.assertIn("Run the test", PAGE)
        self.assertNotIn("sudo", PAGE)

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
        finally:
            server.shutdown()
            server.server_close()
