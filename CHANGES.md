# Open-Model-Card — Change Log

v1.0 rewrite of v0.4. This log tracks the bugs found, fixes applied, and
improvements made during the v1.0 build (2026-10-09).

---

## Bugs found and fixed

### B1 — Page stuck on "Detecting…" and "Probing ports…"

**Symptom**: The SYSTEM region never updated. Model picker said "No models detected yet". The Go button stayed disabled.

**Root cause**: `refreshSystem()` in the page called `post("/api/state", {})`. The `post()` helper hardcodes `method: "POST"`. The server's `/api/state` handler is in `do_GET`, not `do_POST`, so the request hit a 404. The catch block set the engine-list error text but the machine-summary text stayed at its static "Detecting…" default.

**Fix**:
- Added a `getJson(path)` helper to the page that uses `GET` instead of `POST`.
- Changed `refreshSystem()` to call `getJson("/api/state")`.
- Added a fallback handler in `do_POST` for `/api/state` so any client using POST still works.

**Files**: `src/open_model_card/ui.py`, `tests/test_ui.py` (added `test_state_endpoint_via_get`, `test_state_endpoint_via_post`).

---

### B2 — Stale "Run in progress…" banner after a run

**Symptom**: After a run completed (or was interrupted), the yellow resume banner stayed on the page even though `state` was no longer `"running"`. The page's `checkResume()` runs once at page load and only sets the banner; it never hides it after.

**Root cause**: Three contributing factors:
1. The worker thread that runs the test sets `state` to `"done"` or `"error"` only on normal completion. If the worker dies before that (e.g., the server is killed mid-run), the state stays `"running"`.
2. `checkResume()` is a one-shot at page load. It does not re-check or hide the banner when the state changes.
3. The user had no path to dismiss the banner without clicking Discard (which posts to `/api/discard`).

**Fix**:
- The server now tracks the worker thread in `JOB["thread"]`. On every `/api/status` call, if `state == "running"` but the thread is not alive, the server auto-corrects the state to `"error"` with a "run was interrupted" message.
- The page now polls `/api/status` every 3 seconds. The poll handler updates the top lamp, hides the resume banner when state is not `"running"`, and shows it when a run is genuinely in progress.
- `checkResume()` now also explicitly hides the banner when the state is anything other than `"running"`, so a page reload in an idle state starts clean.

**Files**: `src/open_model_card/ui.py`, `tests/test_ui.py` (added `test_stale_running_state_is_corrected`).

---

### B3 — Non-reentrant lock deadlock (caught earlier, kept the fix)

**Symptom**: `/api/status` hung indefinitely after the first `/api/run` was issued.

**Root cause**: `_status_dict()` acquires `JOB_LOCK` internally, and the `/api/status` handler also acquires it. `threading.Lock()` is non-reentrant, so the second acquire blocked forever.

**Fix**: Changed `JOB_LOCK = threading.Lock()` to `JOB_LOCK = threading.RLock()`. (Applied earlier in this session; kept for completeness.)

---

### B4 — Probe URL had a double `/models` (caught earlier)

**Symptom**: `/api/probe` returned HTTP 404 for the Hermes llama.cpp server even though it was reachable.

**Root cause**: The JS sent `url = button.dataset.url.replace(/\/v1\/?$/, "") + "/models"` and the server's `list_models` added another `/models` suffix.

**Fix**: Send `button.dataset.url` (which already includes `/v1`) directly to the probe endpoint. The server treats the URL as a base URL with `/v1`. (Applied earlier in this session.)

---

### B5 — **CRITICAL: Literal newlines inside JS string broke the entire UI**

**Symptom**: After all the other fixes were deployed, the page was STILL stuck on "Detecting… / Probing ports… / No models detected yet". The resume banner showed even when the server's state was "idle". The Go button was disabled. **The JS on the page was not running at all.**

**Root cause**: The PAGE constant in `ui.py` is a Python triple-quoted string. When I wrote `out.textContent = status.plain + "\n\n--- Technical record ---\n\n" + status.markdown;` in the source, the Python source had `\n\n` (4 bytes: backslash + n + backslash + n). In a regular Python string literal, `\n` is the escape sequence for newline (0x0A). So the rendered JS string contained actual newline characters, not the JS escape sequences the browser was expecting.

The browser received:
```js
out.textContent = status.plain + "
                                   (literal newline here)
--- Technical record ---
                                   (literal newline here)
" + status.markdown;
```

This is a JavaScript syntax error. The browser silently fails to execute any of the script. None of the page's interactivity works. The static HTML defaults are all that show.

**Root cause of the root cause**: When I patched the page JS during this session, I used a regular Python string with `\n` for the newlines. I should have used `\\n` (so Python would interpret it as a literal backslash, and JS would interpret it as a newline escape sequence).

**Fix**: Changed the source from `"\n\n--- Technical record ---\n\n"` to `"\\n\\n--- Technical record ---\\n\\n"`. The Python string value now contains `\n` (backslash + n, 2 chars), and the rendered JS string is `"\n\n--- Technical record ---\n\n"`, which JS interprets as two newlines.

**Verification**: Used `node --check` on the rendered JS to confirm it parses. Added `test_page_javascript_parses` as a regression test — it scans every line of the embedded JS and fails if any line has an odd number of unescaped quotes.

**This is the bug that was making the UI unusable. Once fixed, everything else works.**

**Files**: `src/open_model_card/ui.py`, `tests/test_ui.py`.

---

## Improvements made

### I1 — Engine adapters as a registry

- Introduced `src/open_model_card/engines/` package with an `EngineAdapter` base class.
- `LlamaCppAdapter`, `OllamaAdapter`, `OMLXAdapter`, `LMStudioAdapter` registered in `REGISTRY`.
- Adding a new engine is one new file + one `register()` call.

### I2 — Auto-detection

- `discovery.scan_engines()` probes 5 known ports (`18434`, `8080`, `8000`, `11434`, `1234`) and 4 known binaries.
- `scan_installed_apps()` lists engine apps on macOS (Ollama.app, LM Studio.app, etc.).
- Hermes key auto-loads from `~/.hermes/runtimes/llamacpp/server.json` for llama.cpp.

### I3 — Per-model RAM prediction

- `predict.predict()` tries engine API first (`/props` for llama.cpp, `/api/show` for Ollama).
- Falls back to file-size heuristic: `file_size × 1.2 ≈ resident RSS`.
- `predict.fits()` returns ok/ok-but-tight/doesn't-fit with a reason and headroom check.

### I4 — Resource panel always visible

- `resource.collect()` returns a `SystemState` snapshot: total/free RAM, memory pressure, swap.
- Always shown in the SYSTEM region. Updates on every page load.

### I5 — Verdict language

- `schema.speed_verdict(tok_per_s, param_b)` returns "fast" / "average" / "slow" calibrated to model size band.
- Plain summary now reads: "It started answering in 7.9 seconds — fast for this size."

### I6 — Card structure with fingerprints

Every v1.0 card has:
- `schema_version: "1.0"`
- `machine`: OS, arch, total RAM, CPU, GPU, hostname-hash
- `engine`: name, family, version, URL, auth method
- `model`: id, file SHA-256, path, size
- `tasks[]`: each with `comparability: "model-portable"`
- `speed`: with `comparability: "machine-local"`
- `memory`: with `comparability: "machine-local"`

### I7 — Bundle outputs

- `bundle.json` — machine-readable, for the user's agent.
- `bundle.short.md` — ≤500 tokens, fits small context windows.
- `chat-brief.md` — chat-paste-ready with suggested question prompt.
- `chat-brief.md` (clean variant) — strips hostname-hash, SHA-256, paths for public sharing.

### I8 — Comparability filtering

- `compare.filter_same_machine()` keeps only cards from the most-represented machine.
- `compare.filter_cross_machine()` strips `machine-local` fields for cross-machine comparison.
- Comparison table now shows `Model (engine)` column with both name and engine.

### I9 — Retention policy

- `retention.enforce(out_dir, keep=10)` moves older cards to `archive/<engine>/<model>/`.
- 10 newest cards per (engine, model) pair are kept on the main directory.

### I10 — Card filename includes engine

- Old: `20261009T192519Z-Qwen3.6-35B-A3B-UD-Q4_K_M.json`
- New: `20261009T192519Z-llamacpp-Qwen3.6-35B-A3B-UD-Q4_K_M.json`

### I11 — Auto-unload dialog

- Modal pops up when Go is pressed but another model is loaded that we didn't start.
- Default: "No, keep it loaded" (safe).
- Exception: when our app started the engine during a multi-model run, default flips to "Yes, unload and continue."

### I12 — Thinking-aware mode

- `score.score_task()` accepts `thinking_aware=False` (strict) or `True` (relaxes strict format tests).
- The page exposes a "thinking model" checkbox.
- CLI exposes `--thinking-aware`.

### I13 — 12 tests instead of 6

- Old: 6 tests across 5 areas.
- New: 12 tests across 6 areas, including reasoning tests (`reason-bigger`, `reason-deduction`, `reason-sequence`).

---

### I14 — oMLX API key auto-discovery

- **Symptom**: oMLX was detected as a running engine but listed as "needs auth" with HTTP 401. The model picker never showed oMLX models, even though the server was running with 5 MLX models available.
- **Root cause**: oMLX requires an API key (configured in `~/.omlx/settings.json` under `auth.api_key`). The adapter had no way to discover the key; the user had to paste it manually.
- **Fix**: Added `_omlx_key()` to `engines/omlx.py` that reads `~/.omlx/settings.json` (just like `_hermes_key()` does for llama.cpp). Updated `discovery.probe_port()` to auto-load the oMLX key the same way it auto-loads the Hermes key.
- **Result**: oMLX is now reachable on first detection, and all 5 models (Qwen3-14B-MLX-4bit, Qwen3-4B-Instruct-2507-4bit, Qwen3-8B-MLX-4bit, Qwen3.6-35B-A3B-MLX-4bit, gemma-4-E4B-it-MLX-4bit) appear in the model picker without any user action.
- **Test**: `test_omlx_adapter_reads_key_from_settings` — skipped when oMLX is not installed; asserts the adapter probes reachable with the auto-loaded key.

---

## Test coverage

- Before: 14 unit tests.
- After: 63 unit tests.
- New tests cover: engines registry, discovery, resource, predict, schema, retention, bundle, report v1 fields, compare filters, UI state endpoints, stale-state correction.

---

## What is still deferred

- Cross-machine compare UI toggle (compare.filter_cross_machine exists; no button yet)
- Job persistence to disk (currently in-memory only; loses state on server restart)
- Real LM Studio and Ollama live testing (only llama.cpp is running on this Mac)
- Settings UI page (toggles exist in spec but no panel yet)
- Per-machine calibration crowdsourcing for verdict thresholds
