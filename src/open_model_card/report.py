"""Write the JSON and Markdown report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from open_model_card.score import area_summary, strengths


def build_report(meta: dict, speed: dict | None, tasks: list[dict], memory: dict) -> dict:
    return {
        "tool": "open-model-card",
        "version": "0.3.0",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint": meta,
        "speed": speed,
        "memory": memory,
        "tasks": tasks,
        "areas": area_summary(tasks),
        "strengths": strengths(tasks),
        "limits": [
            "Short-prompt speed is not a long-context prefill number.",
            "Task passes are checks, not a general intelligence score.",
            "Memory is the listener process RSS when the OS reports it.",
        ],
    }


def to_markdown(report: dict) -> str:
    meta = report["endpoint"]
    lines = [
        f"# Model card — {meta.get('model')}",
        "",
        f"- Endpoint: `{meta.get('base_url')}`",
        f"- Created: {report['created']}",
        "",
        "## Speed",
        "",
    ]
    speed = report.get("speed") or {}
    if not speed:
        lines.append("Not run.")
    else:
        lines.append(f"- Time to first content token: {speed.get('ttft_s')} s")
        lines.append(f"- Time to first response chunk: {speed.get('ttfr_s')} s")
        lines.append(f"- Generation: {speed.get('tok_per_s')} tok/s over {speed.get('completion_tokens')} tokens")
        lines.append(f"- Wall: {speed.get('wall_s')} s")
        lines.append(f"- Note: {speed.get('note')}")
    lines.extend(["", "## Memory", ""])
    memory = report.get("memory") or {}
    if memory.get("available"):
        lines.append(f"- Listener RSS: {memory.get('rss_mb')} MB")
        lines.append(f"- PIDs: {', '.join(memory.get('pids') or [])}")
    else:
        lines.append(f"- Not measured: {memory.get('reason', 'unavailable')}")
    lines.extend(["", "## Tasks", ""])
    lines.append("| Task | Area | Result | Detail |")
    lines.append("|---|---|---|---|")
    for row in report.get("tasks") or []:
        mark = "pass" if row["pass"] else "fail"
        detail = str(row["detail"]).replace("|", "/")
        lines.append(f"| {row['id']} | {row['area']} | {mark} | {detail} |")
    found = report.get("strengths") or {}
    lines.extend(
        [
            "",
            "## Where this run was strongest",
            "",
            ", ".join(found.get("best") or []) or "No area was a clean pass.",
            "",
            "## Where this run was weakest",
            "",
            ", ".join(found.get("weak") or []) or "No area failed every check.",
            "",
            "## Limits",
            "",
        ]
    )
    for item in report.get("limits") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["created"].replace(":", "").replace("-", "")
    model = str(report["endpoint"].get("model") or "model").replace("/", "-")
    stem = f"{stamp}-{model}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, md_path
