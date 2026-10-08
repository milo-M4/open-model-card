"""Rule scoring for the fixed task suite.

Scores are checks a person can re-read. They are not a general IQ number.
"""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def score_exact(text: str, expected: str) -> dict[str, Any]:
    got = text.strip()
    ok = got == expected
    return {"pass": ok, "detail": f"got {got!r}" if not ok else "exact match"}


def score_json(text: str, expected: dict) -> dict[str, Any]:
    got = extract_json_object(text)
    if got is None:
        return {"pass": False, "detail": "no JSON object"}
    missing = [key for key in expected if got.get(key) != expected[key]]
    extra = [key for key in got if key not in expected]
    ok = not missing and not extra
    detail = "object matched" if ok else f"missing_or_wrong={missing} extra={extra}"
    return {"pass": ok, "detail": detail}


def score_digits(text: str, expected: str) -> dict[str, Any]:
    digits = re.sub(r"\D", "", text)
    ok = digits == expected
    return {"pass": ok, "detail": f"digits={digits!r} expected={expected!r}"}


def score_facts(text: str, required: list[str], forbidden: list[str]) -> dict[str, Any]:
    missing = [item for item in required if item not in text]
    present_forbidden = [item for item in forbidden if item in text]
    ok = not missing and not present_forbidden
    return {
        "pass": ok,
        "detail": f"missing={missing} forbidden_present={present_forbidden}",
    }


def score_hyphen_lines(text: str, count: int) -> dict[str, Any]:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    bad = [line for line in lines if not line.startswith("- ")]
    ok = len(lines) == count and not bad
    return {"pass": ok, "detail": f"lines={len(lines)} bad={bad[:3]}"}


def score_task(task: dict, text: str) -> dict[str, Any]:
    kind = task["kind"]
    if kind == "exact":
        result = score_exact(text, task["expected"])
    elif kind == "json":
        result = score_json(text, task["expected"])
    elif kind == "digits":
        result = score_digits(text, task["expected"])
    elif kind == "facts":
        result = score_facts(text, task["required"], task["forbidden"])
    elif kind == "hyphen_lines":
        result = score_hyphen_lines(text, task["count"])
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
