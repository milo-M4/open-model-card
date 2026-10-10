# open-model-card — Test Plan

## How we build test plans

When Charlie says "develop a test plan," the workflow is:

1. **Read the code.** Every test references actual functions, not guesses.
2. **Write the plan into a file.** The file lives in the repo so the next operator can see it.
3. **Execute the tests.** Unit tests run before any server is touched. Live tests need a model loaded and the server running.
4. **Record results.** Pass or fail. No narrative replaces tool output.
5. **Commit.** Tests + plan + results go into the repo together.

This is not a paper exercise. A test plan is a list of functions to call with specific inputs, then verify the output matches what the spec says.

## Current test coverage

| File | What it tests | Type |
|---|---|---|
| `tests/test_score.py` | Score functions — exact, json, digits, facts, hyphen_lines. Compare rules. Guard block_reason. Brief output. | Unit (no server) |
| `tests/test_ui.py` | PAGE contains expected text. Panel serves HTTP 200 on localhost. | Unit (http server) |

No tests exist yet for: `client.py` (stream_speed, complete, unload_model), `report.py` (build_report, write_report, plain_summary, to_markdown), `guard.py` (find_block — the live port scan path), `brief.py` (agent_brief — the full output), `compare.py` (comparison_markdown, plain_choice, load_reports), `hostmem.py` (rss_mb_for_port).

## Test plan sections

### A. Score checks (test_score.py) — DONE

All 8 score functions are tested. The compare rules are tested with two synthetic cards. The guard logic is tested with two synthetic resident lists. The brief output is tested for blank notes.

**Result:** PASS. 6 test methods covering all 5 score kinds, compare rules, guard, and brief.

### B. UI panel (test_ui.py) — DONE

PAGE contains "STEP 1", "Where is the model running?", "appearance: none", "Pause routines, cron jobs", "I have paused other routines". Panel serves HTTP 200 on 127.0.0.1.

**Result:** PASS. 2 test methods.

### C. Score output formatting (report.py) — MISSING

- `build_report` produces the expected keys: `tool`, `version`, `created`, `endpoint`, `speed`, `memory`, `tasks`, `areas`, `strengths`, `limits`.
- `to_markdown` includes the model name, speed metrics, memory, task table, strengths, and limits sections.
- `plain_summary` includes sentences about speed, memory, pass count, per-area pass/fail, and unload status.
- `write_report` creates one `.json` and one `.md` file in the output directory with the correct timestamped model name stem.

### D. Comparison output (compare.py) — PARTIAL

compare rules are tested via the `recommend` → `advice` dict in `test_score.py`. Missing: `comparison_markdown` produces a table with model, pass rate, tok/s, RSS, stable. `plain_choice` returns the three job labels with model names. `load_reports` reads `.json` files from a directory and returns the list in sorted order.

### E. Client HTTP paths (client.py) — MISSING

- `_request` raises `EndpointError` on non-200 status with the status code and first 500 bytes of the body.
- `_request` raises `EndpointError` on connection refused (URLError).
- `complete` returns `{"text": ..., "elapsed_s": ..., "usage": ...}`.
- `stream_speed` returns `ttfr_s`, `ttft_s`, `wall_s`, `tok_per_s`, `completion_tokens`, `text_preview`.
- `list_models` returns model IDs from a `/models` response.
- `unload_model` does not raise — it catches `EndpointError` and returns `{"attempted": True, "unloaded": False, ...}`.

### F. Guard live path (guard.py) — PARTIAL

`block_reason` is tested with two synthetic resident lists. `find_block` calls `model_rows` then falls back to `rss_mb_for_port` when the endpoint is unreachable. Missing test for `find_block` — it touches the filesystem and network, so it needs a mock or a live test flag.

### G. Host memory (hostmem.py) — MISSING

- `rss_mb_for_port` returns `{"available": False, "reason": "lsof or ps not on PATH"}` when `lsof` or `ps` is missing.
- `rss_mb_for_port` returns `{"available": False, "reason": "nothing listening on $port"}` when nothing is on the port.
- `rss_mb_for_port` returns `{"available": True, "pids": [...], "rss_mb": ..., "platform": ...}` when a process is listening.

### H. End-to-end smoke test (requires server) — MISSING

1. Start a model on port 18434.
2. Run `open-model-card --base-url http://127.0.0.1:18434/v1 --model Qwen3.6-35B-A3B-UD-Q4_K_M --api-key ...`
3. Verify `reports/` contains one `.json` and one `.md` with the correct filename stem.
4. Verify `.json` has `tool: "open-model-card"`, `tasks` has 6 entries, `areas` has 6 entries.
5. Verify `plain_summary` contains sentences, not just numbers.
6. Press **Compare saved cards** (CLI or panel). Verify `reports/choice.md` and `reports/agent-brief.md` are written.
7. Verify the card writer calls `unload_model` at the end and the summary says whether it succeeded.

## How to run these tests

```bash
cd /Users/milo/Milo-Workspace/code/open-model-card
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

This runs all unit tests. No server is required.

For end-to-end smoke tests, load a model on a port first, then use the CLI or the panel.

## Rules for adding tests

- Always add a test when you add a function. No new code without coverage.
- Unit tests must not touch the network. If a test needs a server, put it in a separate file marked `tests/test_live.py` and skip it by default.
- Keep tests deterministic. No timestamps, no random numbers.
- A test that passes by catching an exception is better than one that passes because the code is right. Explicit `assertRaises` wins.

## Recommended improvements

These are ordered by impact. The highest-impact items are missing tests or broken code paths.

### Critical — bugs found during live use (2026-10-08)

1. **Preset buttons did not auto-fill the Hermes key**
   - Clicking "Hermes llama.cpp" set `use_hermes_key = false`, sending no key to the server, which returned 401.
   - Fix: When `data-url` includes `:18434`, set `window.useHermesKey = true` and update the status line.
   - Status: **APPLIED** (see commit below).
   - Test: Add `test_ui.py::test_hermes_button_sets_key` to verify `data-url` buttons set the flag.

2. **oMLX /models endpoint returns 401 without a key**
   - This is a server config issue, not a panel bug. The panel correctly forwarded the request.
   - Improvement: Add a status indicator next to each preset button showing whether the server responded successfully (green = reachable, red = unreachable/auth fail).

### High — missing tests (coverage gaps)

3. **client.py — no tests for HTTP paths**
   - `complete` — mock `_request`, verify `{"text": ..., "elapsed_s": ..., "usage": ...}`.
   - `stream_speed` — mock `urlopen`, verify `ttfr_s`, `ttft_s`, `tok_per_s`.
   - `unload_model` — mock `_request` to raise `EndpointError`, verify no exception and `{"unloaded": False}`.
   - `list_models` — mock `_request`, verify model ID extraction.

4. **report.py — no tests for output formatting**
   - `build_report` — verify all keys present.
   - `to_markdown` — verify model name, speed, memory, task table sections exist.
   - `plain_summary` — verify sentences, not just numbers.
   - `write_report` — verify `.json` and `.md` files created with correct stem.

5. **compare.py — missing tests for markdown and loading**
   - `comparison_markdown` — verify table format with model, pass rate, tok/s, RSS, stable.
   - `plain_choice` — verify three job labels with model names.
   - `load_reports` — verify sorted `.json` file reading from a directory.

6. **guard.py — missing `find_block` live path test**
   - `block_reason` is tested. `find_block` calls `model_rows` then falls back to `rss_mb_for_port`.
   - Need a test with mocked `model_rows` raising `EndpointError` and a listening port with known RSS.

7. **hostmem.py — no tests**
   - Three cases: `lsof`/`ps` missing, nothing listening, process listening with RSS.

### Medium — usability improvements

8. **Preset button status indicators**
   - Add a small circle next to each preset (green = reachable, red = unreachable) so the user knows which buttons will work before clicking "List models."

9. **Error messages for common failures**
   - 401 → "That server requires a password. Enter it above or press 'Use the Hermes key on this Mac'."
   - Connection refused → "That server is not running. Start it, then try again."
   - Timeout → "The server took too long. Check that the model is loaded."

10. **Saved model files — clickable to fill the model field**
    - Currently "Show saved model files" only prints paths. Clicking a path should fill the model select dropdown.

11. **Report download links**
    - After a test, the readout should include a "Download card as Markdown" button.

### Low — housekeeping

12. **Version bump**
    - `report.py` hardcodes `"version": "0.4.0"`. Keep it in sync with the package version.

13. **Skip live tests in CI**
    - `tests/test_live.py` does not exist yet. When added, mark all tests with `@unittest.skipUnless` so CI passes without a server.

14. **Test plan execution record**
    - Update the execution table above each time a new section is completed.

### Implementation order

1. Fix preset button key issue → DONE (commit in progress)
2. Add tests for `client.py` complete, stream_speed, unload_model
3. Add tests for `report.py` build_report, to_markdown, plain_summary, write_report
4. Add tests for `compare.py` comparison_markdown, plain_choice, load_reports
5. Add test for `guard.py` find_block with mocked model_rows + live RSS fallback
6. Add tests for `hostmem.py`
7. Add `tests/test_live.py` for end-to-end smoke test (sections C–H of the plan)
8. Add preset button status indicators (usability)
9. Add clickable saved model files (usability)

## Test plan execution record

| Date | Section | Status | Notes |
|---|---|---|---|
| 2026-10-08 | A. Score checks | PASS | 6 methods, all 5 score kinds + compare + guard + brief |
| 2026-10-08 | B. UI panel | PASS | 2 methods, text presence + HTTP serve |
| 2026-10-08 | C. Report formatting | NOT STARTED | See plan above |
| 2026-10-08 | D. Compare output | PARTIAL | Rules tested via recommend. Markdown and plain_choice not tested. load_reports not tested. |
| 2026-10-08 | E. Client HTTP | NOT STARTED | All paths listed above. |
| 2026-10-08 | F. Guard live path | PARTIAL | block_reason tested. find_block needs mock. |
| 2026-10-08 | G. Host memory | NOT STARTED | Missing the 3 cases listed above. |
| 2026-10-08 | H. End-to-end smoke | NOT STARTED | Needs a live model on a port. |
| 2026-10-09 | A. Score checks | PASS | v1.0 rewrite: 12 tests, thinking-aware, contains, numbered_lines. 19 methods. |
| 2026-10-09 | C. Report formatting | PASS | v1.0 card schema with machine/engine/model fingerprints. |
| 2026-10-09 | D. Compare output | PASS | New: filter_same_machine, filter_cross_machine, comparison_markdown includes engine. |
| 2026-10-09 | E. Client HTTP | PARTIAL | Engines adapters tested. list_models, model_size, unload tested via live probes. |
| 2026-10-09 | F. Guard live path | PASS | guard.is_model_loaded + guard.find_loaded_model tested live. find_block kept for legacy. |
| 2026-10-09 | G. Host memory | PASS | resource.collect + top_consumers tested. |
| 2026-10-09 | H. End-to-end smoke | PASS | Live card via /api/run: 9/12 in 37s, v1.0 schema, all fingerprints. |
| 2026-10-09 | I. v1.0 modules | PASS | schema, engines, discovery, resource, predict, bundle, retention, comparability, retention, schema_version. 49 new methods. |
| 2026-10-09 | J. UI bug fixes | PASS | B1 (POST→GET), B2 (stale state), B3 (RLock), B4 (probe URL). |
