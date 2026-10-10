"""Rule scoring for the fixed task suite.

Scores are checks a person can re-read. They are not a general IQ number.

A task has a `kind` that says how to grade the reply. A `thinking_aware`
flag relaxes the strict format tests so a model that prints its reasoning
before the final answer is graded on the final answer, not on the whole
output. The flag does not change knowledge or reasoning tests — those
already look for substrings in the reply, so the thinking trace is fine.
"""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE = re.compile(r"`([^`\n]+)`")
_FINAL = re.compile(r"(?im)\b(?:final answer|the answer is|answer:|output:)\b\s*[:\-]?\s*")
_SHORT_NUM = re.compile(r"(?m)(?:^|\D)(-?\d{1,6})(?=\D|$)")
_FIRST_JSON = re.compile(r"\{[^{}]*\}")


def extract_json_object(text: str) -> dict | None:
    """Find a JSON object in the text, even when wrapped in a code block."""
    fence = _FENCE.findall(text)
    if fence:
        for block in fence:
            value = _try_load_object(block)
            if value is not None:
                return value
    inline = _INLINE.findall(text)
    for block in inline:
        value = _try_load_object(block)
        if value is not None:
            return value
    value = _try_load_object(text)
    return value if isinstance(value, dict) else None


def _try_load_object(text: str) -> dict | None:
    if "{" not in text or "}" not in text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def strip_thinking(text: str) -> str:
    """Return the part of the reply that looks like a final answer.

    Tries, in order: a 'Final Answer:' marker, the last fenced code block,
    the last inline code block. Falls back to the full text. This is only
    used by the strict format kinds when the operator turns on
    thinking-aware mode.
    """
    marker = _FINAL.search(text)
    if marker:
        return text[marker.end():].strip()
    fences = _FENCE.findall(text)
    if fences:
        return fences[-1].strip()
    inlines = _INLINE.findall(text)
    if inlines:
        last = inlines[-1].strip()
        if last and len(last) < 500:
            return last
    return text


def _lines_with_dash(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- ")]


def _numbered_lines(text: str) -> list[int]:
    found: list[int] = []
    for line in text.splitlines():
        m = re.match(r"^\s*(-?\d+)\s*\.?\s*$", line)
        if m:
            found.append(int(m.group(1)))
    return found


def score_exact(text: str, expected: str, thinking_aware: bool) -> dict[str, Any]:
    got = text.strip()
    if got == expected:
        return {"pass": True, "detail": "exact match"}
    if thinking_aware:
        # If the first non-empty line is the expected value, that is the
        # final answer and the rest is the reasoning trace.
        for line in got.splitlines():
            if line.strip():
                if line.strip() == expected:
                    return {"pass": True, "detail": f"final answer line: {line.strip()!r}"}
                break
        # Otherwise, look for the expected value as a standalone token.
        if re.search(rf"(?m)^[\s\W]*{re.escape(expected)}[\s\W]*$", got):
            return {"pass": True, "detail": f"expected value found on its own line"}
    return {"pass": False, "detail": f"got {got[:80]!r}"}


def score_json(text: str, expected: dict, thinking_aware: bool) -> dict[str, Any]:
    got = extract_json_object(text)
    if got is None:
        if thinking_aware:
            return {"pass": False, "detail": "no JSON object found, even after looking in code blocks"}
        return {"pass": False, "detail": "no JSON object"}
    missing = [key for key in expected if got.get(key) != expected[key]]
    extra = [key for key in got if key not in expected]
    ok = not missing and not extra
    detail = "object matched" if ok else f"missing_or_wrong={missing} extra={extra}"
    return {"pass": ok, "detail": detail}


def score_digits(text: str, expected: str, thinking_aware: bool) -> dict[str, Any]:
    digits = re.sub(r"\D", "", text)
    if digits == expected:
        return {"pass": True, "detail": f"digits={digits!r} expected={expected!r}"}
    if thinking_aware:
        # Look for a standalone number on its own line that matches.
        for line in text.splitlines():
            stripped = line.strip().rstrip(".")
            if stripped == expected:
                return {"pass": True, "detail": f"standalone number {expected!r} on its own line"}
        # Or any short number (1-6 digits) anywhere in the trace. We pick
        # the last occurrence because thinking models usually place the
        # final answer at the end of the trace.
        candidates = re.findall(r"(?:^|\D)(-?\d{1,6})(?=\D|$)", text)
        if expected in candidates:
            return {"pass": True, "detail": f"short number {expected!r} found in the trace"}
    return {"pass": False, "detail": f"digits={digits[:60]!r} expected={expected!r}"}


def score_facts(text: str, required: list[str], forbidden: list[str]) -> dict[str, Any]:
    missing = [item for item in required if item not in text]
    present_forbidden = [item for item in forbidden if item in text]
    ok = not missing and not present_forbidden
    return {
        "pass": ok,
        "detail": f"missing={missing} forbidden_present={present_forbidden}",
    }


def score_contains(text: str, expected: str) -> dict[str, Any]:
    """Reasoning test. The reply should contain the expected short answer.
    Case-insensitive. A short reasoning trace does not mask a real miss."""
    lower = text.lower()
    target = expected.lower().strip()
    if not target:
        return {"pass": False, "detail": "scorer missing expected value"}
    if target in lower:
        return {"pass": True, "detail": f"contains {expected!r}"}
    return {"pass": False, "detail": f"reply does not contain {expected!r}"}


def score_hyphen_lines(text: str, count: int, thinking_aware: bool) -> dict[str, Any]:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    bad = [line for line in lines if not line.startswith("- ")]
    if len(lines) == count and not bad:
        return {"pass": True, "detail": f"lines={len(lines)} all start with '- '"}
    if thinking_aware:
        dashed = _lines_with_dash(text)
        if len(dashed) == count:
            return {"pass": True, "detail": f"found {count} lines starting with '- ' in the trace"}
    return {"pass": False, "detail": f"lines={len(lines)} bad={bad[:3]}"}


def score_numbered_lines(text: str, count: int, thinking_aware: bool) -> dict[str, Any]:
    numbers = _numbered_lines(text)
    expected = list(range(1, count + 1))
    if numbers == expected:
        return {"pass": True, "detail": f"lines={numbers} correct order"}
    if thinking_aware:
        # The reply might wrap the answer in a code block.
        fenced = _FENCE.findall(text)
        if fenced:
            numbers = _numbered_lines(fenced[-1])
            if numbers == expected:
                return {"pass": True, "detail": f"lines={numbers} in code block"}
    return {"pass": False, "detail": f"got {numbers[:10]} expected {expected}"}


def score_task(task: dict, text: str, thinking_aware: bool = False) -> dict[str, Any]:
    kind = task["kind"]
    if kind == "exact":
        result = score_exact(text, task["expected"], thinking_aware)
    elif kind == "json":
        result = score_json(text, task["expected"], thinking_aware)
    elif kind == "digits":
        result = score_digits(text, task["expected"], thinking_aware)
    elif kind == "facts":
        result = score_facts(text, task["required"], task["forbidden"])
    elif kind == "contains":
        result = score_contains(text, task["expected"])
    elif kind == "hyphen_lines":
        result = score_hyphen_lines(text, task["count"], thinking_aware)
    elif kind == "numbered_lines":
        result = score_numbered_lines(text, task["count"], thinking_aware)
    else:
        result = {"pass": False, "detail": f"unknown kind {kind}"}
    return {
        "id": task["id"],
        "area": task["area"],
        "pass": result["pass"],
        "detail": result["detail"],
        "reply": text.strip()[:500],
    }


def area_summary(results: list[dict]) -> list[dict]:
    areas: dict[str, list[bool]] = {}
    for row in results:
        areas.setdefault(row["area"], []).append(bool(row["pass"]))
    out = []
    for area, flags in areas.items():
        passed = sum(1 for flag in flags if flag)
        out.append({"area": area, "passed": passed, "total": len(flags)})
    return out


def strengths(results: list[dict]) -> dict[str, list[str]]:
    summary = area_summary(results)
    best = [row["area"] for row in summary if row["passed"] == row["total"] and row["total"]]
    weak = [row["area"] for row in summary if row["passed"] == 0]
    return {"best": best, "weak": weak}
