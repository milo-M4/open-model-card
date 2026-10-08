"""Fixed tasks. Same prompts on every machine so cards can be compared.

This is not MMLU and not a leaderboard. A pass means the model did the
small thing we asked. A fail means it did not.
"""

from __future__ import annotations

TASKS = [
    {
        "id": "exact-reply",
        "area": "instruction following",
        "kind": "exact",
        "prompt": "Reply with exactly this text and nothing else: BENCHOK",
        "expected": "BENCHOK",
    },
    {
        "id": "json-object",
        "area": "structured output",
        "kind": "json",
        "prompt": (
            'Return only a JSON object, no markdown, with keys '
            '"action" and "path". action must be "read". path must be "notes.md".'
        ),
        "expected": {"action": "read", "path": "notes.md"},
    },
    {
        "id": "arithmetic",
        "area": "exact calculation",
        "kind": "digits",
        "prompt": "What is 17 times 23? Reply with digits only.",
        "expected": "391",
    },
    {
        "id": "faithful-summary",
        "area": "faithfulness",
        "kind": "facts",
        "prompt": (
            "Summarize this in one sentence. Include the date and the invoice "
            "amount. Do not add any other date or amount.\n\n"
            "The pump was replaced on March 3. The invoice was $240. The tech was named Lee."
        ),
        "required": ["March 3", "240"],
        "forbidden": ["April", "500"],
    },
    {
        "id": "meeting-facts",
        "area": "transcript accuracy",
        "kind": "facts",
        "prompt": (
            "Extract only the decisions from this meeting. Include each decision. "
            "Do not add a decision that was not said.\n\n"
            "Alex: Ship the badge order Friday.\n"
            "Blair: Hold the newsletter.\n"
            "Alex: Budget stays at 50 dollars."
        ),
        "required": ["Friday", "newsletter", "50"],
        "forbidden": ["Monday", "100"],
    },
    {
        "id": "three-lines",
        "area": "format control",
        "kind": "hyphen_lines",
        "prompt": "Reply with exactly 3 lines. Each line must start with '- '.",
        "count": 3,
    },
]
