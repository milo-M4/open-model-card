# open-model-card

A repeatable report card for a model already running on your machine.

It talks to any OpenAI-compatible `/v1` endpoint (llama.cpp, oMLX, Ollama, vLLM). It writes a Markdown file and a JSON file you can compare later. It does not download a model and it does not start a server.

This is not a second copy of [llama-benchy](https://github.com/eugr/llama-benchy). That tool is the right one for prompt-processing and generation speed at many context depths. This tool answers a different question: on this machine, right now, how fast is a short reply, how much memory is the server using, and does the model do five small checks.

It is also not [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) or [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness). Those are for research evals. This is a card you can run again after you change a quant, a runtime, or a machine.

## What it measures

| Area | Check | What a pass means |
|---|---|---|
| Speed | Time to first content token, tokens per second, wall time | A short prompt only. Not an 8k prefill. |
| Memory | RSS of the process listening on the port | Host efficiency, when the OS reports it. |
| Instruction following | Reply is exactly `BENCHOK` | It obeyed a tight instruction. |
| Structured output | JSON object with the asked keys and values | It can emit a tool-shaped object. |
| Exact calculation | Digits for 17 × 23 are `391` | It did not invent a nearby number. |
| Faithfulness | Summary keeps March 3 and 240, and does not add April or 500 | It did not decorate the source. |
| Format control | Exactly 3 lines, each starting with `- ` | It held a format. |

There is no single intelligence score. The card says which of those areas passed.

## Run

Python 3.11 or newer. No extra packages.

```bash
python3 -m open_model_card --list-criteria
```

From a checkout:

```bash
PYTHONPATH=src python3 -m open_model_card \
  --base-url http://127.0.0.1:18434/v1 \
  --model Qwen3.6-35B-A3B-UD-Q4_K_M \
  --api-key "$OPENAI_API_KEY"
```

Or, after `pip install .`:

```bash
open-model-card --base-url http://127.0.0.1:8000/v1 --model your-model
```

Reports land in `./reports/` as one `.md` and one `.json`. That directory is gitignored so a local run is not committed.

Do not load two large models at once. This tool will not unload a model for you. If the endpoint needs a key, pass `--api-key` or set `OPENAI_API_KEY`. The key is not written into the report.

## What this will not tell you

- How the model does at 8k or 64k prefill. Use llama-benchy for that.
- Whether it is good at law, medicine, or your private documents.
- A ranking against a published leaderboard.

Run one model at a time. Save each card. Then compare them:

```bash
PYTHONPATH=src python3 -m open_model_card --compare reports
```

That writes `reports/choice.md` and `reports/agent-brief.md`. The brief is the file you hand to Hermes, or any agent you already use. This tool does not call a model to write it.

Copy `operator.md.example` to `reports/operator.md` and fill in how you work before you compare. If that file is missing, the brief says the notes are blank and tells the reviewing agent not to guess.

The reviewing agent is instructed to recommend per job, cite the table, refuse to pair two 20 GB models, and say when a real transcript is still required.


| Job | Rule |
|---|---|
| Transcripts | Must keep the short meeting facts. Then the highest task pass rate. Speed is only a tie-break. |
| Operator | Must follow the exact instruction and emit the JSON object. Then the highest pass rate. |
| Light cron | Must follow the exact instruction, must not be a 20 GB resident, then the fastest. |

A model that returns an empty reply is unstable and is not chosen. A 20 GB model is marked so you do not load two of them. The meeting check is a short extract, not your real transcripts. If two models tie there, judge them on one real transcript before you pin that cron job.

For long-prompt speed, use [llama-benchy](https://github.com/eugr/llama-benchy). This card will not pretend a short count is an 8k prefill.

