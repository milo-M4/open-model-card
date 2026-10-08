# open-model-card

A repeatable report card for a model that is already running on your machine.

It talks to any OpenAI-compatible `/v1` endpoint (llama.cpp, oMLX, Ollama, vLLM). It writes a Markdown file and a JSON file. It does not download a model and it does not start a server.

There is no Mac, Windows, or Linux installer. Python 3.11 or newer is the one requirement, so the same checkout runs on all three. A double-click package can come later. Developers should extend this library rather than wrapping a binary.

## Why this exists

Speed at many context depths is already covered by [llama-benchy](https://github.com/eugr/llama-benchy). Research accuracy is already covered by [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) and [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness). Those tools were not rebuilt here.

The missing piece was a card a person can run on the computer in front of them, compare later, and hand to an agent they already use. This repo is that card.

## What a pass means

There is no single intelligence score. A pass means the model did the small thing we asked. A fail means it did not. The checks are the same on every machine so two cards can be compared.

| Area | Check | Why this check |
|---|---|---|
| Speed | Time to first content token, tokens per second, wall time | A short prompt. Not an 8k prefill. Long-prompt speed belongs to llama-benchy. |
| Memory | RSS of the process listening on the port | Host efficiency, when the OS reports it. A listener RSS misses a child process, so a llama.cpp router can look small while the model is large. |
| Instruction following | Reply is exactly `BENCHOK` | An operator that cannot hold a tight instruction will not hold a cron prompt. |
| Structured output | JSON object with the asked keys and values | Tool use needs a shaped object, not a paragraph about one. |
| Exact calculation | Digits for 17 × 23 are `391` | A nearby number is a fail. |
| Faithfulness | Summary keeps March 3 and 240, and does not add April or 500 | Decoration of a source is a fail. |
| Transcript accuracy | Short meeting extract keeps Friday, newsletter, and 50, and does not add Monday or 100 | A proxy for transcript work. It is not a real transcript suite. |
| Format control | Exactly 3 lines, each starting with `- ` | Format drift is a fail. |

## One model at a time

A test loads a model into memory. Only one model should be resident.

- Before a run, pause routines, cron jobs, and other agent chats. If you do not, the test can fail or that other work can fail.
- The panel will not start a run if another model is still loaded. It names what is still resident.
- Testing the same model on the same server again is allowed. That does not load a second copy.
- When the test finishes, the card asks a llama.cpp router to unload that model (`POST /models/unload`). Other servers may refuse. The summary says which happened.
- The tool will not unload a model another agent is already using. Cutting that work off is how a mail check or a transcript job fails. The test stops instead. You pause that work yourself.

Hermes may also unload a quiet llama.cpp model after about 15 minutes. That is too slow if you want to test the next model now. Do not rely on it.

## How a recommendation is made

Compare does not pick one winner for every job. The rules are in `compare.py` so a contributor can change them without guessing.

| Job | Rule | Why |
|---|---|---|
| Transcripts | Must keep the short meeting facts. Then the highest task pass rate. Speed only breaks a tie. | A fast model that drops a decision is the wrong model for this job. |
| Operator | Must follow the exact instruction and emit the JSON object. Then the highest pass rate. | Day-to-day work is tool-shaped. |
| Light cron | Must follow the exact instruction, must not be a 20 GB resident, then the fastest. | A large model held all day for mail is the collision this tool exists to avoid. |

An empty reply is unstable and is not chosen. A model at or above 20 GB is marked so two of them are not paired.

If two models tie on the short meeting extract, judge them on one real transcript before pinning that job. This card will not pretend the extract is that transcript.

## Hand the brief to your own agent

This tool does not call a model to write the recommendation. The operator fills in how they work. Their agent reads the file.

1. Copy `operator.md.example` to `reports/operator.md` and fill it in.
2. Run `open-model-card --compare reports`, or press **Compare saved cards**.
3. Give `reports/agent-brief.md` to the agent you already use.
4. Say: read this brief and recommend a model for my jobs. Use only the numbers in the file. Do not invent a score.

If the notes are still the blank template, the brief says so and tells the agent not to guess.

## Control panel

```bash
cd open-model-card
PYTHONPATH=src python3 -m open_model_card --ui
```

On Windows, if `python3` is not the command, use `py -m open_model_card --ui`.

Open http://127.0.0.1:8765. The page binds to this machine only. Do not publish it. It can ask a local server to run a model.

The page is a terminal-looking control panel on purpose: dark ground, amber keys, a status lamp. The labels are plain language because the first users are people learning local models, not people who want a second command line. macOS was drawing unlabeled system buttons, so keys set `appearance: none` and use dark text on amber. Hover keeps the label visible.

Three steps:

1. Where the model is already running. Preset keys fill Hermes llama.cpp (`18434`), oMLX (`8000`), or Ollama (`11434`).
2. Which model. **List models** asks that server. **Show saved model files** looks in the usual folders and does not load a file. **Use the Hermes key on this Mac** reads the local runtime key on the server side. The key is not shown and is not written into the report.
3. Check the box that other work is paused, then **Run the test**. **Compare saved cards** reads the JSON cards already saved.

While a test runs, the lamp blinks and the line next to it names the current check and the seconds elapsed. A quiet page does not mean the test stopped.

The readout leads with sentences. The technical table follows, under a line that says it can be skipped.

## Command line

```bash
PYTHONPATH=src python3 -m open_model_card --list-criteria

PYTHONPATH=src python3 -m open_model_card \
  --base-url http://127.0.0.1:18434/v1 \
  --model your-model \
  --api-key "$OPENAI_API_KEY"

PYTHONPATH=src python3 -m open_model_card --compare reports --profile reports/operator.md
```

After `pip install .`, the command is `open-model-card`. Reports land in `./reports/` and that directory is gitignored.

## For contributors

The library is the product. The page is a caller.

| Module | Role |
|---|---|
| `tasks.py` | The fixed prompts. Change these and you change what "pass" means. Keep them deterministic. |
| `score.py` | Rule checks. No second model grades the first. |
| `client.py` | HTTP to `/v1/chat/completions`, plus llama.cpp unload. |
| `guard.py` | Refuse a run while another model is resident. |
| `compare.py` | Per-job rules. Do not collapse these into one score. |
| `brief.py` | The file an outside agent reads. Do not add a model call here. |
| `report.py` | JSON, technical Markdown, and the plain sentences. |
| `ui.py` | The panel. Keep labels in plain language. Do not bind beyond `127.0.0.1`. |

Tests are stdlib `unittest`. `PYTHONPATH=src python3 -m unittest discover -s tests -v`.

Do not add a dependency for a check the standard library can do. Do not auto-unload a model that another process is using. Do not invent a leaderboard number from this suite.
