# Open-Model-Card v1.0 — Status Snapshot

**Date:** 2026-10-09
**Branch:** `main` (working tree dirty, nothing committed)
**Live server:** `http://127.0.0.1:8765` (PID 2880)
**Tests:** 65/65 unit tests pass
**Spec doc:** `/Users/milo/Milo-Workspace/Sig Core/scratch/Open-Model-Card Scope.md`
**UI guide:** `/Users/milo/Milo-Workspace/Sig Core/scratch/open-model-card-ui-guide.html`

---

## What we built (v1.0)

A single-page web app that:
1. Auto-detects local model servers (llama.cpp, Ollama, oMLX, LM Studio) on common ports
2. Auto-loads their API keys (Hermes llama.cpp from `server.json`, oMLX from `settings.json`)
3. Shows what's reachable, with version info
4. Lets the user pick an engine+model, runs a 12-test battery + speed measurement
5. Writes a v1.0 card with full fingerprints (machine, engine, model) to `reports/`
6. Generates three outputs: `bundle.json` (machine-readable), `bundle.short.md` (≤500 tokens for the user's agent), `chat-brief.md` (chat-paste-ready)

The user picks a single (engine, model) pair, runs the test, gets a card. Compare across cards is available.

---

## What works (verified live)

| Path | What | Status |
|---|---|---|
| `http://127.0.0.1:8765/` | Page renders, JS executes, no syntax errors | ✓ |
| `/api/state` (GET) | Returns machine fingerprint, 5 engines, 2 installed apps | ✓ |
| `/api/status` (GET) | Job state polling | ✓ |
| `/api/predict` (POST) | Per-model RAM prediction, fits check | ✓ |
| `/api/run` (POST) | Start a test, returns job_id | ✓ |
| `/api/compare` (POST) | Bundle + recommendation | ✓ |
| `/api/copy/agent\|chat\|clean` (POST) | Three export formats | ✓ |
| `/api/engines/add` (POST) | Manual engine override | partial (logs but doesn't persist) |
| Engine detection | llama.cpp (1 model), oMLX (5 models) auto-discovered | ✓ |
| Engine auth | Hermes key + oMLX key auto-loaded | ✓ |
| Card writer | v1.0 schema with machine/engine/model fingerprints | ✓ |
| Retention | Keep last 10 cards per (engine, model) | ✓ (untested in browser) |
| Resume banner | Auto-hides on idle, polls every 3s | ✓ |
| Model picker | Auto-selects first model | ✓ |
| Resource check | Shows "won't fit" or "go anyway" | ✓ |

---

## What we found and fixed this session

| # | Bug | Fix |
|---|---|---|
| B1 | `/api/state` was GET only; the page sent POST → 404 → "Detecting…" stuck | Added `getJson()` helper, made page use GET, added POST fallback |
| B2 | "Run in progress…" banner stuck when server state was idle | Track worker thread, auto-correct to "error" if dead; poll every 3s to hide banner |
| B3 | Non-reentrant `Lock()` deadlock on `/api/status` | Changed to `RLock()` |
| B4 | Probe URL had double `/models` | Send base URL directly, server handles `/v1/models` |
| B5 | **CRITICAL**: JS string had unterminated quotes due to Python `\n` vs `\\n` escape bug | Changed source to `\\n\\n` (Python produces `\n` literal, JS interprets as newline) |
| B6 | CSS specificity bug: `.resume { display: flex }` defined after `.hidden { display: none }`, so the hidden class had no effect | Added `!important` to `.hidden` |
| — | UX: "Won't fit" button was disabled, leaving no way to override | Now enabled with "Go anyway" |
| — | UX: model picker required user to click before resource check showed | Now auto-selects first model |
| — | UX: radio buttons looked like mystery boxes | Wrapped in labeled pills with backgrounds |
| — | Feature: oMLX adapter couldn't find its key | Added `_omlx_key()` reading `~/.omlx/settings.json` |

---

## What we have NOT done

### Not implemented (deferred per spec)
- Cross-machine compare UI toggle (the code exists, no button)
- Job persistence to disk (in-memory only — server restart loses state)
- Settings UI panel (toggles exist in spec, no page)
- Ollama / LM Studio live testing (servers not running on this Mac)
- "Add custom engine" doesn't persist the key
- "Run anyway" warning to user about unload consequences

### Not committed
- All 13+ changes are uncommitted in the working tree
- No PR, no commit message drafted
- Both spec/UI-guide docs in Sig Core scratch are v1.0; need to decide whether to keep both v0.4 and v1.0 or replace

### Not tested by hand
- **The actual browser experience** — I've been testing via curl and `node --check`, not by loading the page in a real browser interactively
- **Multi-model mode** — only single-model is exercised
- **Real oMLX test run** — discovered the key but haven't run the 12-test battery against an oMLX model
- **Compare panel interactivity** — `bundle.json` is written but I haven't tested the modal in a real browser
- **Resume after browser close** — spec says jobs/ persistence; not done

---

## Files in the working tree (uncommitted)

```
modified:  src/open_model_card/cli.py
modified:  src/open_model_card/client.py
modified:  src/open_model_card/compare.py
modified:  src/open_model_card/discovery.py
modified:  src/open_model_card/guard.py
modified:  src/open_model_card/report.py
modified:  src/open_model_card/score.py
modified:  src/open_model_card/tasks.py
modified:  src/open_model_card/ui.py
modified:  tests/test_score.py
modified:  tests/test_ui.py
new:       src/open_model_card/schema.py
new:       src/open_model_card/resource.py
new:       src/open_model_card/predict.py
new:       src/open_model_card/bundle.py
new:       src/open_model_card/retention.py
new:       src/open_model_card/engines/__init__.py
new:       src/open_model_card/engines/llamacpp.py
new:       src/open_model_card/engines/ollama.py
new:       src/open_model_card/engines/omlx.py
new:       src/open_model_card/engines/lmstudio.py
new:       tests/test_v1.py
new:       CHANGES.md
new:       STATUS.md        (this file)
```

Plus in Sig Core scratch:
```
modified:  Open-Model-Card Scope.md        (v0.4 → v1.0)
modified:  open-model-card-ui-guide.html   (v0.4 → v1.0)
```

---

## What I want you to test

1. **Reload `http://127.0.0.1:8765/`** in your browser. Tell me:
   - Does the SYSTEM panel populate within 1-2 seconds?
   - Are 5 engines shown, with oMLX as green/reachable?
   - Is the model picker populated with all 6 models (1 llama.cpp + 5 oMLX)?

2. **Pick a small oMLX model** (e.g., `Qwen3-4B-Instruct-2507-4bit`) and click Go. This is the smallest model (~3 GB) so it should fit easily. Tell me:
   - Does the test run? (~30-60s)
   - Does the card appear in RESULTS?
   - Does the plain summary read well?

3. **Try a larger oMLX model** (`Qwen3.6-35B-A3B-MLX-4bit`). The "Will use" line will show ~22 GB. Probably won't fit in current free RAM. Tell me:
   - Does "Go anyway" work?
   - Does the resource check make sense?

4. **Click Compare saved cards.** Tell me:
   - Does the modal open?
   - Does the table make sense?
   - Does the recommendation pick a model per job?

5. **Click a card's Copy for my agent / Copy for a chatbot / Copy clean.** Tell me:
   - Does anything appear in your clipboard?
   - Does the chat-brief make sense as something you'd paste into a chatbot?

---

## What you might find broken (suspected)

- **Compare modal might overflow** if there are 10+ cards
- **"Run again" button** on a card might not work if `selectedEngine` / `selectedModel` isn't set
- **Multi-model mode** is untested
- **Auto-refresh during a long run** — the polling hides the resume banner when state goes back to idle, but I haven't seen this in action

---

## What I'd like your feedback on

1. **Should we commit now**, or are there more bugs to find?
2. **Should the v0.4 scope doc / UI guide be preserved** (as `*-v0.4.md`) or replaced?
3. **Do you want a guided tour** where I drive the browser test for you (curl + simulate the page) so we can find more bugs before you load the page?
4. **Are there engines on this Mac I missed?** (Any other model servers running that the discovery didn't find?)

---

## Next session, if any

1. Run the full 12-test battery against an oMLX model
2. Test the multi-model mode
3. Wire up the cross-machine compare toggle
4. Add job persistence to disk
5. Add the Settings panel
6. Commit on `main` with a meaningful commit message
