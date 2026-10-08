"""A briefing an operator can hand to an agent they already use.

This module does not call a model. The operator fills in how they work.
Their agent reads the file and makes the custom recommendation.
"""

from __future__ import annotations

from pathlib import Path

OPERATOR_TEMPLATE = """# Operator notes

Fill this in before you hand the brief to your agent. Delete the prompts you do not need.

- Machine:
- Jobs this model must do:
- Jobs that can be small and fast:
- What must not fail:
- What you will not pay for:
- How you like work done:
- Models you refuse to run at the same time:
"""

AGENT_RULES = """You are reviewing a local model bench for this operator. Use only the measurements and the operator notes in this file.

- Recommend one model per job the operator named. If they did not name a job, use transcripts, operator, and light cron.
- Cite the pass rate, tokens per second, and memory from the table. Do not invent a benchmark number.
- Do not treat the short meeting extract as a real transcript suite. If transcript accuracy is the job and two models tie, say a real transcript is still required.
- A model at or above 20 GB is a large model. Do not recommend running two of them at once.
- An empty or unstable run is not a candidate.
- If the operator notes are still the blank template, say what is missing and do not guess their work.
- Do not tell them to turn safety approvals off.
"""


def read_operator_notes(path: Path | None) -> tuple[str, bool]:
    if path is None or not path.is_file():
        return OPERATOR_TEMPLATE.strip(), False
    text = path.read_text(encoding="utf-8").strip()
    return text or OPERATOR_TEMPLATE.strip(), True


def agent_brief(comparison: str, operator_notes: str, notes_filled: bool) -> str:
    filled = "The operator wrote the notes below." if notes_filled else "The operator notes are still the blank template."
    return "\n".join([
        "# Agent brief — local model choice",
        "",
        "Hand this file to the agent you already use. This tool did not call a model to write it.",
        "",
        "## Instructions for the reviewing agent",
        "",
        AGENT_RULES.strip(),
        "",
        f"Note status: {filled}",
        "",
        "## Operator",
        "",
        operator_notes.strip(),
        "",
        "## Measured cards",
        "",
        comparison.strip(),
        "",
    ])
