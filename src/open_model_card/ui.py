"""Local control panel. Binds to this machine only. Does not call a review model."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from open_model_card.brief import agent_brief, read_operator_notes
from open_model_card.cli import run_card
from open_model_card.client import EndpointError, list_models
from open_model_card.compare import comparison_markdown, load_reports, plain_choice, recommend
from open_model_card.discover import find_model_files
from open_model_card.report import plain_summary, to_markdown

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
  .lamp { width: 0.9rem; height: 0.9rem; border-radius: 50%; background: #9dff8a; box-shadow: 0 0 8px #9dff8a; display: inline-block; }
  .lamp.busy { background: #e6c15a; box-shadow: 0 0 8px #e6c15a; animation: pulse 1s steps(2) infinite; }
  @keyframes pulse { 50% { opacity: 0.25; } }
  .panel { border: 1px solid #2f6b38; margin-top: 1rem; padding: 1rem; background: #0c120d; }
  .step { color: #e6c15a; font-size: 0.85rem; letter-spacing: 0.12em; }
  h2 { margin: 0.2rem 0 0.6rem; font-size: 1.15rem; }
  p.help { color: #b7d7ae; margin: 0 0 0.7rem; }
  label { display: block; margin: 0.7rem 0 0.25rem; }
  input, select, button { font: inherit; }
  label input { width: auto; margin-right: 0.4rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.65rem;
    background: #071008; color: #d7f5c8; border: 1px solid #3d8f4a;
  }
  .keys { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.8rem; }
  button {
    appearance: none;
    -webkit-appearance: none;
    background: #e6c15a;
    color: #14180c;
    border: 2px solid #e6c15a;
    padding: 0.75rem 1rem;
    cursor: pointer;
    font-weight: 700;
  }
  button:hover, button:focus { background: #fff1b8; color: #14180c; outline: 2px solid #9dff8a; }
  button.primary { background: #9dff8a; color: #14180c; border-color: #9dff8a; }
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
    <p class="help">This test loads a model into memory. Only one model can be loaded at a time. When the test finishes, this panel asks that server to unload it.</p>
    <p class="help">It will not unload a model another agent is already using. If one is still loaded, the test stops instead of cutting that work off.</p>
    <p class="help">Pause routines, cron jobs, and other agent chats before you run a test. If you do not, the test can fail, or that other work can fail.</p>
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
    <div class="keys">
      <button type="button" id="hermeskey">Use the Hermes key on this Mac</button>
    </div>
    <p class="help" id="keynote">The key stays on this computer. It is not shown here.</p>
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
    <label><input id="paused" type="checkbox"> I have paused other routines, cron jobs, and agent chats.</label>
    <div class="keys">
      <button type="button" class="primary" id="run">Run the test</button>
      <button type="button" id="compare">Compare saved cards</button>
    </div>
  </section>

  <section class="panel">
    <div class="step">READOUT</div>
    <h2>Result</h2>
    <p id="status"><span class="lamp" id="lamp"></span> <span id="statusText">Idle. Start with step 1.</span></p>
    <pre id="out">The plain summary will appear here. The technical record follows it.</pre>
  </section>
</main>
<script>
const out = document.getElementById("out");
function payload() {
  return {
    base_url: document.getElementById("base").value,
    api_key: document.getElementById("key").value,
    model: document.getElementById("model").value,
    use_hermes_key: window.useHermesKey === true
  };
}
function plain(err) {
  const msg = String(err && err.message || err);
  if (msg.indexOf("401") >= 0 || msg.indexOf("API Key") >= 0) {
    return "That server wants a password. Paste it above, or press Use the Hermes key on this Mac.";
  }
  if (msg.indexOf("could not reach") >= 0) {
    return "That server is not running. Start it, then press List models again.";
  }
  return msg;
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
  button.onclick = () => {
    document.getElementById("base").value = button.dataset.url;
    window.useHermesKey = false;
  };
});
document.getElementById("hermeskey").onclick = () => {
  window.useHermesKey = true;
  document.getElementById("keynote").textContent = "Hermes key will be used from this Mac. It is not shown.";
};
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
    out.textContent = plain(err);
  }
};
document.getElementById("scan").onclick = async () => {
  const data = await post("/api/scan");
  out.textContent = data.files.length
    ? "Saved files. These are not loaded.\\n\\n" + data.files.join("\\n")
    : "No model files in the usual folders. You can still test a model that a server is already running.";
};
document.getElementById("run").onclick = async () => {
  if (!document.getElementById("paused").checked) {
    out.textContent = "Pause other routines, cron jobs, and agent chats first. Then check the box and press Run the test. This test loads a model. Only one model can be in memory.";
    return;
  }
  const lamp = document.getElementById("lamp");
  const statusText = document.getElementById("statusText");
  lamp.className = "lamp busy";
  statusText.textContent = "Starting. The light stays on while the test is working.";
  out.textContent = "Working. A quiet page does not mean it stopped. Watch the light and the line above.";
  try {
    await post("/api/run", payload());
    while (true) {
      const status = await fetch("/api/status").then((res) => res.json());
      const elapsed = status.elapsed_s == null ? "" : " (" + status.elapsed_s + "s)";
      statusText.textContent = (status.step || "Working") + elapsed;
      if (status.state === "done") {
        lamp.className = "lamp";
        statusText.textContent = "Finished.";
        out.textContent = status.plain + "\n\n--- Technical record ---\n\n" + status.markdown;
        return;
      }
      if (status.state === "error") {
        lamp.className = "lamp";
        statusText.textContent = "Stopped.";
        out.textContent = plain({ message: status.error });
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (err) {
    lamp.className = "lamp";
    statusText.textContent = "Stopped.";
    out.textContent = plain(err);
  }
};
document.getElementById("compare").onclick = async () => {
  out.textContent = "Reading saved cards...";
  try {
    const data = await post("/api/compare");
    out.textContent = data.plain + "\n\n--- Side-by-side record ---\n\n" + data.table;
  } catch (err) {
    out.textContent = err.message;
  }
};
</script>
</body>
</html>
"""


def _key(data: dict) -> str:
    typed = data.get("api_key") or ""
    if typed or not data.get("use_hermes_key"):
        return typed
    path = Path.home() / ".hermes" / "runtimes" / "llamacpp" / "server.json"
    if not path.is_file():
        raise EndpointError("No Hermes key file on this Mac.")
    saved = json.loads(path.read_text(encoding="utf-8")).get("api_key") or ""
    if not saved:
        raise EndpointError("The Hermes key file has no key.")
    return saved


JOB = {"state": "idle", "step": "Idle", "started": 0.0, "error": "", "plain": "", "markdown": ""}
JOB_LOCK = threading.Lock()


def _status() -> dict:
    with JOB_LOCK:
        elapsed = None
        if JOB["state"] == "running" and JOB["started"]:
            elapsed = round(time.time() - JOB["started"], 1)
        return {
            "state": JOB["state"],
            "step": JOB["step"],
            "elapsed_s": elapsed,
            "error": JOB["error"],
            "plain": JOB["plain"],
            "markdown": JOB["markdown"],
        }


def _start_run(data: dict, out_dir: Path) -> None:
    with JOB_LOCK:
        if JOB["state"] == "running":
            return
        JOB.update(state="running", step="Starting", started=time.time(), error="", plain="", markdown="")

    def work() -> None:
        try:
            def progress(message: str) -> None:
                with JOB_LOCK:
                    JOB["step"] = message

            report = run_card(
                data.get("base_url") or "",
                data.get("model") or "",
                _key(data),
                180,
                out_dir,
                False,
                False,
                progress,
            )
            with JOB_LOCK:
                JOB["plain"] = plain_summary(report)
                JOB["markdown"] = to_markdown(report)
                JOB["step"] = "Finished"
                JOB["state"] = "done"
        except Exception as exc:  # noqa: BLE001 — the panel has to show the failure
            with JOB_LOCK:
                JOB["error"] = str(exc)
                JOB["step"] = "Stopped"
                JOB["state"] = "error"

    threading.Thread(target=work, daemon=True).start()


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
        if urlparse(self.path).path == "/api/status":
            self._json(200, _status())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self._read()
            if path == "/api/models":
                models = list_models(data.get("base_url") or "", _key(data), 15)
                self._json(200, {"models": models})
                return
            if path == "/api/scan":
                self._json(200, {"files": find_model_files()})
                return
            if path == "/api/run":
                from open_model_card.guard import find_block

                reason = find_block(data.get("base_url") or "", data.get("model") or "", _key(data))
                if reason:
                    self._json(409, {"error": reason})
                    return
                _start_run(data, self.out_dir)
                self._json(200, {"started": True})
                return
            if path == "/api/compare":
                reports = load_reports(self.out_dir)
                if not reports:
                    self._json(400, {"error": "No saved cards yet. Run a test first. Compare reads those saved cards."})
                    return
                advice = recommend(reports)
                text = comparison_markdown(reports, advice)
                notes, filled = read_operator_notes(self.out_dir / "operator.md")
                brief = agent_brief(text, notes, filled)
                (self.out_dir / "choice.md").write_text(text, encoding="utf-8")
                (self.out_dir / "agent-brief.md").write_text(brief, encoding="utf-8")
                self._json(200, {"plain": plain_choice(advice), "table": text, "brief": brief})
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
