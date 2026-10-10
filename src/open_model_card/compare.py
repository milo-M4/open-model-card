"""Compare saved cards and recommend a model per job.

The recommendation is a rule, not a hidden score. If the evidence is missing,
the rule says so instead of picking a winner.

Supports both v1.0 cards (with model/engine fingerprints) and v0.4 cards
(legacy endpoint.base_url). v0.4 cards can't be cross-machine filtered
because they have no machine fingerprint.
"""

from __future__ import annotations

import json
from pathlib import Path

from open_model_card.schema import MACHINE_LOCAL


LARGE_RSS_MB = 20000


def load_reports(directory: Path) -> list[dict]:
    reports = []
    for path in sorted(directory.glob("*.json")):
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    return reports


def _model(report: dict) -> str:
    """Model name. Reads v1 first, falls back to v0.4 endpoint.model."""
    v1 = (report.get("model") or {}).get("id")
    if v1:
        return str(v1)
    return str((report.get("endpoint") or {}).get("model") or "unknown")


def _engine(report: dict) -> str:
    """Engine family + name. Returns 'unknown' for legacy v0.4 cards."""
    e = report.get("engine") or {}
    name = e.get("name") or e.get("family") or "unknown"
    family = e.get("family") or "unknown"
    return f"{family}:{name}"


def _machine_host(report: dict) -> str:
    m = report.get("machine") or {}
    return m.get("hostname_hash") or "unknown"


def filter_same_machine(reports: list[dict]) -> list[dict]:
    """Return only the cards from the most-represented machine.

    Used for the default compare view.
    """
    counts: dict[str, int] = {}
    for r in reports:
        h = _machine_host(r)
        counts[h] = counts.get(h, 0) + 1
    if not counts:
        return reports
    main = max(counts.items(), key=lambda kv: kv[1])[0]
    return [r for r in reports if _machine_host(r) == main]


def filter_cross_machine(reports: list[dict]) -> list[dict]:
    """Strip machine-local fields from every card for cross-machine view."""
    import copy
    out = []
    for r in reports:
        r2 = copy.deepcopy(r)
        if "speed" in r2:
            r2["speed"] = None
        if "memory" in r2:
            r2["memory"] = {"comparability": MACHINE_LOCAL, "available": False, "reason": "hidden in cross-machine compare"}
        out.append(r2)
    return out


def _area_passed(report: dict, area: str) -> bool | None:
    rows = [row for row in report.get("areas") or [] if row.get("area") == area]
    if not rows:
        return None
    return all(row["passed"] == row["total"] for row in rows)


def _pass_rate(report: dict) -> float | None:
    tasks = report.get("tasks") or []
    if not tasks:
        return None
    return sum(1 for row in tasks if row.get("pass")) / len(tasks)


def _tok_s(report: dict) -> float | None:
    speed = report.get("speed") or {}
    value = speed.get("tok_per_s")
    return float(value) if isinstance(value, (int, float)) else None


def _rss(report: dict) -> float | None:
    memory = report.get("memory") or {}
    if not memory.get("available"):
        return None
    value = memory.get("rss_mb")
    return float(value) if isinstance(value, (int, float)) else None


def _stable(report: dict) -> bool:
    tasks = report.get("tasks") or []
    if not tasks:
        return False
    return all(str(row.get("reply") or "").strip() for row in tasks)


def _line(report: dict, reason: str) -> dict:
    return {"model": _model(report), "reason": reason, "report": report}


def recommend(reports: list[dict]) -> dict:
    """Pick per job. A job can have no qualified model."""
    stable = [report for report in reports if _stable(report)]
    transcripts = [
        report for report in stable
        if _area_passed(report, "transcript accuracy") is True
        and _area_passed(report, "faithfulness") is not False
    ]
    operator = [
        report for report in stable
        if _area_passed(report, "instruction following") is True
        and _area_passed(report, "structured output") is True
    ]
    cron = [
        report for report in stable
        if _area_passed(report, "instruction following") is True
        and (_rss(report) is None or _rss(report) < LARGE_RSS_MB)
    ]
    # Prefer a known-small model for cron. Unknown RSS stays eligible but is labeled.
    known_small = [report for report in cron if _rss(report) is not None and _rss(report) < 8000]

    def fastest(pool: list[dict]) -> dict | None:
        if not pool:
            return None
        return max(pool, key=lambda report: _tok_s(report) or 0)

    def most_accurate(pool: list[dict]) -> dict | None:
        if not pool:
            return None
        return max(pool, key=lambda report: (_pass_rate(report) or 0, _tok_s(report) or 0))

    transcript_pick = most_accurate(transcripts)
    operator_pick = most_accurate(operator)
    cron_pool = known_small or cron
    cron_pick = fastest(cron_pool)

    def why_missing(job: str) -> str:
        if not reports:
            return "No cards in the folder."
        if not stable:
            return "Every card had an empty reply. That is an unstable run. Do not choose from it."
        return f"No card qualified for {job}."

    return {
        "transcripts": _choice(transcript_pick, "highest task pass rate among models that kept the meeting facts", why_missing("transcripts")),
        "operator": _choice(operator_pick, "highest task pass rate among models that followed instructions and emitted the JSON object", why_missing("operator")),
        "cron": _choice(
            cron_pick,
            "fastest model that followed instructions and is not a 20 GB resident"
            + ("" if known_small else "; memory was missing, so this is not proven small"),
            why_missing("cron"),
        ),
        "do_not_pair": [
            _model(report) for report in reports if (_rss(report) or 0) >= LARGE_RSS_MB
        ],
    }


def _choice(report: dict | None, reason: str, missing: str) -> dict:
    if report is None:
        return {"model": None, "reason": missing}
    note = reason
    rss = _rss(report)
    if rss is not None and rss >= LARGE_RSS_MB:
        note += f". It used {rss:.0f} MB. Do not load another large model beside it."
    return {
        "model": _model(report),
        "engine": _engine(report),
        "machine": _machine_host(report),
        "reason": note,
        "pass_rate": _pass_rate(report),
        "tok_per_s": _tok_s(report),
        "rss_mb": rss,
    }


def plain_choice(advice: dict) -> str:
    labels = {
        "transcripts": "For meeting transcripts",
        "operator": "For day-to-day work that must follow instructions",
        "cron": "For light repeating jobs",
    }
    lines = ["Here is the side-by-side result.", ""]
    for job, label in labels.items():
        choice = advice.get(job) or {}
        model = choice.get("model") or "no model yet"
        lines.append(f"{label}: {model}. {choice.get('reason')}")
    paired = advice.get("do_not_pair") or []
    if paired:
        lines.append("")
        lines.append("Do not run these at the same time: " + ", ".join(paired) + ".")
    lines.extend([
        "",
        "To ask your own agent, give it the file reports/agent-brief.md.",
        "Say: Read this brief and recommend a model for my jobs. Use only the numbers in the file. Do not invent a score.",
        "If the operator notes in that file are still blank, fill them in first or the agent will not know your work.",
    ])
    return "\n".join(lines)


def comparison_markdown(reports: list[dict], advice: dict) -> str:
    lines = [
        "# Model choice",
        "",
        "One large model at a time. This is a guide from the cards on disk, not a leaderboard.",
        "",
        "| Model (engine) | Pass rate | tok/s | RSS MB | Stable |",
        "|---|---|---|---|---|",
    ]
    for report in reports:
        rate = _pass_rate(report)
        model = _model(report)
        engine = _engine(report)
        label = f"{model} ({engine})" if engine != "unknown:unknown" else model
        lines.append(
            f"| {label} | "
            f"{'n/a' if rate is None else f'{rate:.0%}'} | "
            f"{_tok_s(report) if _tok_s(report) is not None else 'n/a'} | "
            f"{_rss(report) if _rss(report) is not None else 'n/a'} | "
            f"{'yes' if _stable(report) else 'no'} |"
        )
    lines.extend(["", "## Recommendation", ""])
    for job in ("transcripts", "operator", "cron"):
        choice = advice[job]
        model = choice.get("model") or "none"
        engine = choice.get("engine") or ""
        label = f"{model} ({engine})" if engine and engine != "unknown:unknown" else model
        lines.append(f"- **{job}:** {label}. {choice.get('reason')}")
    paired = advice.get("do_not_pair") or []
    if paired:
        lines.append("")
        lines.append("Do not run these at the same time: " + ", ".join(paired) + ".")
    lines.extend([
        "",
        "Transcript advice here is a short meeting extract, not your real transcripts. If two models tie on that check, judge them on one real transcript before you pin the cron job.",
        "",
    ])
    return "\n".join(lines)
