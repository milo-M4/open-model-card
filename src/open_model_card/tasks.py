"""Fixed tasks. Same prompts on every machine so cards can be compared.

This is not MMLU and not a leaderboard. A pass means the model did the
small thing we asked. A fail means it did not.

Twelve model tests across six areas. Speed and host memory are recorded
alongside them, so the report shows fourteen checks total — matching the
panel guide.
"""

from __future__ import annotations

TASKS = [
    # exact_reply x2 — instruction following, exact format
    {
        "id": "exact-reply-benchok",
        "area": "instruction following",
        "kind": "exact",
        "prompt": "Reply with exactly this text and nothing else: BENCHOK",
        "expected": "BENCHOK",
    },
    {
        "id": "exact-reply-single-token",
        "area": "instruction following",
        "kind": "exact",
        "prompt": "Reply with exactly this text and nothing else: HELIX42",
        "expected": "HELIX42",
    },
    # json_output x2 — structured output
    {
        "id": "json-action-path",
        "area": "structured output",
        "kind": "json",
        "prompt": (
            'Return only a JSON object, no markdown, with keys '
            '"action" and "path". action must be "read". path must be "notes.md".'
        ),
        "expected": {"action": "read", "path": "notes.md"},
    },
    {
        "id": "json-customer-tier",
        "area": "structured output",
        "kind": "json",
        "prompt": (
            'Return only a JSON object, no markdown, with keys '
            '"tier" and "renews". tier must be "gold". renews must be "2027-01-15".'
        ),
        "expected": {"tier": "gold", "renews": "2027-01-15"},
    },
    # counting x1 — exact calculation
    {
        "id": "arithmetic-17x23",
        "area": "exact calculation",
        "kind": "digits",
        "prompt": "What is 17 times 23? Reply with digits only.",
        "expected": "391",
    },
    # knowledge x2 — faithfulness + transcript accuracy
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
    # reasoning x3 — short logic problems, answer is a small word or short phrase
    {
        "id": "reason-bigger",
        "area": "reasoning",
        "kind": "contains",
        "prompt": (
            "Which is larger, 0.6 or 2/3? "
            "Reply with only the larger number written as a decimal, no words."
        ),
        "expected": "0.67",
    },
    {
        "id": "reason-deduction",
        "area": "reasoning",
        "kind": "contains",
        "prompt": (
            "All bloops are razzies. All razzies are lazzes. "
            "Is a bloop a lazze? Reply with one word: yes or no."
        ),
        "expected": "yes",
    },
    {
        "id": "reason-sequence",
        "area": "reasoning",
        "kind": "contains",
        "prompt": (
            "Continue the pattern: 2, 4, 8, 16, ?. "
            "Reply with only the next number, no words."
        ),
        "expected": "32",
    },
    # format_control x2 — output format strictness
    {
        "id": "three-hyphen-lines",
        "area": "format control",
        "kind": "hyphen_lines",
        "prompt": "Reply with exactly 3 lines. Each line must start with '- '.",
        "count": 3,
    },
    {
        "id": "five-numbered-lines",
        "area": "format control",
        "kind": "numbered_lines",
        "prompt": "Reply with exactly 5 lines. Each line must be a single number 1, 2, 3, 4, 5 on its own line, in that order. No other text.",
        "count": 5,
    },
]
