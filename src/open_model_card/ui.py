"""Local control panel. Binds to this machine only. Does not call a review model."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from open_model_card.brief import agent_brief, read_operator_notes
from open_model_card.cli import run_card
from open_model_card.client import EndpointError, list_models
from open_model_card.compare import comparison_markdown, load_reports, recommend
from open_model_card.discover import find_model_files
from open_model_card.report import to_markdown

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Open Model Card</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; min-height: 100vh;
    background: #10140f;
    color: #d7f5c8;
    font: 18px/1.45 "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
  }
  main { max-width: 56rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
  header { display: flex; justify-content: space-between; gap: 1rem; align-items: center; border-bottom: 2px solid #3d8f4a; padding-bottom: 0.8rem; }
  h1 { font-size: 1.4rem; letter-spacing: 0.08em; margin: 0; color: #9dff8a; }
  .lamp { width: 0.8rem; height: 0.8rem; border-radius: 50%; background: #9dff8a; box-shadow: 0 0 8px #9dff8a; display: inline-block; }
  .panel { border: 1px solid #2f6b38; margin-top: 1rem; padding: 1rem; background: #0c120d; }
  .step { color: #e6c15a; font-size: 0.85rem; letter-spacing: 0.12em; }
  h2 { margin: 0.2rem 0 0.6rem; font-size: 1.15rem; }
  p.help { color: #b7d7ae; margin: 0 0 0.7rem; }
  label { display: block; margin: 0.7rem 0 0.25rem; }
  input, select, button { font: inherit; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.65rem;
    background: #071008; color: #d7f5c8; border: 1px solid #3d8f4a;
  }
  .keys { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.8rem; }
  button {
    background: #142016; color: #9dff8a; border: 1px solid #3d8f4a;
    padding: 0.7rem 0.9rem; cursor: pointer;
  }
  button:hover, button:focus { background: #1d3a22; outline: 2px solid #e6c15a; }
  button.primary { background: #1d3a22; color: #fff8dc; border-color: #e6c15a; }
  .warn { border-color: #e6c15a; color: #ffe7a3; }
  pre {
    white-space: pre-wrap; min-height: 8rem; margin: 0;
    background: #070d08; color: #d7f5c8; padding: 1rem; border: 1px solid #2f6b38;
  }
</style>
</head>
<body>
<main>
  <header>
    <h1>OPEN MODEL CARD</h1>
    <span><span class="lamp"></span> LOCAL ONLY</span>
  </header>
  <section class="panel warn">
    <p class="help">Test one model at a time. This panel will not turn another model off for you. A test can take several minutes and can load a large model. A file found on the computer is not a model that is running.</p>
  </section>

  <section class="panel">
    <div class="step">STEP 1</div>
    <h2>Where is the model running?</h2>
    <p class="help">Pick the program that is already serving the model. You do not type a command.</p>
    <div class="keys">
      <button type="button" data-url="http://127.0.0.1:18434/v1">Hermes llama.cpp</button>
      <button type="button" data-url="http://127.0.0.1:8000/v1">oMLX</button>
      <button type="button" data-url="http://127.0.0.1:11434/v1">Ollama</button>
    </div>
    <label for="base">Address</label>
    <input id="base" value="http://127.0.0.1:18434/v1">
    <label for="key">Password for that server, if it asks for one</label>
    <input id="key" type="password" autocomplete="off">
  </section>

  <section class="panel">
    <div class="step">STEP 2</div>
    <h2>Which model?</h2>
    <p class="help">List the models that server can run, then choose one. Or look at files saved on this computer. Looking does not load them.</p>
    <label for="model">Model</label>
    <select id="model"><option value="">List models first</option></select>
    <div class="keys">
      <button type="button" id="list">List models</button>
      <button type="button" id="scan">Show saved model files</button>
    </div>
  </section>

  <section class="panel">
    <div class="step">STEP 3</div>
    <h2>Run, then read</h2>
    <p class="help">Run writes a card. Compare reads the cards you have already saved and writes a brief you can hand to your own agent.</p>
    <div class="keys">
      <button type="button" class="primary" id="run">Run the test</button>
      <button type="button" id="compare">Compare saved cards</button>
    </div>
  </section>

  <section class="panel">
    <div class="step">READOUT</div>
    <h2>Result</h2>
    <pre id="out">Ready. Start with step 1.</pre>
  </section>
</main>
<script>
const out = document.getElementById("out");
function payload() {
  return {
    base_url: document.getElementById("base").value,
    api_key: document.getElementById("key").value,
    model: document.getElementById("model").value
  };
}
async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
document.querySelectorAll("[data-url]").forEach((button) => {
  button.onclick = () => { document.getElementById("base").value = button.dataset.url; };
});
document.getElementById("list").onclick = async () => {
  out.textContent = "Asking the server which models it has...";
  try {
    const data = await post("/api/models", payload());
    const sel = document.getElementById("model");
    sel.innerHTML = "";
    if (!data.models.length) {
      out.textContent = "That server did not list a model. Check that it is running, then try again.";
      return;
    }
    for (const id of data.models) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      sel.appendChild(opt);
    }
    out.textContent = "Choose a model in step 2, then press Run the test.";
  } catch (err) {
    out.textContent = "Could not reach that server. " + err.message;
  }
};
document.getElementById("scan").onclick = async () => {
  const data = await post("/api/scan");
  out.textContent = data.files.length
    ? "Saved files. These are not loaded.\\n\\n" + data.files.join("\\n")
    : "No model files in the usual folders. You can still test a model that a server is already running.";
};
document.getElementById("run").onclick = async () => {
  out.textContent = "Running. This can take several minutes. Leave this page open.";
  try {
    const data = await post("/api/run", payload());
    out.textContent = data.markdown;
  } catch (err) {
    out.textContent = err.message;
  }
};
document.getElementById("compare").onclick = async () => {
  out.textContent = "Reading saved cards...";
  try {
    const data = await post("/api/compare");
    out.textContent = data.brief;
  } catch (err) {
    out.textContent = err.message;
  }
};
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    out_dir = Path("reports")

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self._read()
            if path == "/api/models":
                models = list_models(data.get("base_url") or "", data.get("api_key") or "", 15)
                self._json(200, {"models": models})
                return
            if path == "/api/scan":
                self._json(200, {"files": find_model_files()})
                return
            if path == "/api/run":
                report = run_card(
                    data.get("base_url") or "",
                    data.get("model") or "",
                    data.get("api_key") or "",
                    180,
                    self.out_dir,
                    False,
                    False,
                )
                self._json(200, {"markdown": to_markdown(report), "model": report["endpoint"]["model"]})
                return
            if path == "/api/compare":
                reports = load_reports(self.out_dir)
                if not reports:
                    self._json(400, {"error": "No saved cards yet. Run a test first."})
                    return
                text = comparison_markdown(reports, recommend(reports))
                notes, filled = read_operator_notes(self.out_dir / "operator.md")
                brief = agent_brief(text, notes, filled)
                (self.out_dir / "choice.md").write_text(text, encoding="utf-8")
                (self.out_dir / "agent-brief.md").write_text(brief, encoding="utf-8")
                self._json(200, {"brief": brief})
                return
        except EndpointError as exc:
            self._json(400, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — show the failure on the panel
            self._json(500, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})


def serve(out_dir: Path, port: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    Handler.out_dir = out_dir
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Open http://127.0.0.1:{port}")
    print("This panel is only on this machine. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()
