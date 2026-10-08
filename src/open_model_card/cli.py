"""Command line."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from open_model_card.client import EndpointError, complete, list_models, stream_speed
from open_model_card.hostmem import rss_mb_for_port
from open_model_card.report import build_report, to_markdown, write_report
from open_model_card.score import score_task
from open_model_card.tasks import TASKS


def run_card(base_url: str, model: str, api_key: str, timeout: float, out: Path, skip_speed: bool, skip_tasks: bool, progress=None) -> dict:
    def note(message: str) -> None:
        if progress:
            progress(message)

    note("Asking the server which model to test")
    chosen = model or (list_models(base_url, api_key, timeout) or [""])[0]
    if not chosen:
        raise EndpointError("No model id. Pass a model name.")
    speed = None
    if not skip_speed:
        note("Measuring how fast a short reply starts and finishes")
        speed = stream_speed(base_url, chosen, api_key, timeout)
    rows = []
    if not skip_tasks:
        for task in TASKS:
            note(f"Checking {task['area']}")
            result = complete(base_url, chosen, task["prompt"], api_key, timeout)
            rows.append(score_task(task, result["text"]))
    note("Writing the card")
    port = urlparse(base_url).port or 80
    report = build_report({"base_url": base_url, "model": chosen}, speed, rows, rss_mb_for_port(port))
    json_path, md_path = write_report(report, out)
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a repeatable report card for a local OpenAI-compatible model."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:18434/v1")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--out", default="reports")
    parser.add_argument("--skip-speed", action="store_true")
    parser.add_argument("--skip-tasks", action="store_true")
    parser.add_argument("--list-criteria", action="store_true")
    parser.add_argument("--compare", default="", help="Directory of report JSON files to rank")
    parser.add_argument("--profile", default="", help="Operator notes markdown to include in the agent brief")
    parser.add_argument("--ui", action="store_true", help="Open a local page to pick a model, run, and compare")
    parser.add_argument("--ui-port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.compare:
        from open_model_card.brief import agent_brief, read_operator_notes
        from open_model_card.compare import comparison_markdown, load_reports, recommend

        folder = Path(args.compare)
        reports = load_reports(folder)
        advice = recommend(reports)
        text = comparison_markdown(reports, advice)
        out = folder / "choice.md"
        out.write_text(text, encoding="utf-8")
        profile = Path(args.profile) if args.profile else folder / "operator.md"
        notes, filled = read_operator_notes(profile if profile.is_file() else None)
        brief_path = folder / "agent-brief.md"
        brief_path.write_text(agent_brief(text, notes, filled), encoding="utf-8")
        print(text)
        print(f"Wrote {out}")
        print(f"Wrote {brief_path}")
        return 0 if reports else 2

    if args.ui:
        from open_model_card.ui import serve

        serve(Path(args.out), args.ui_port)
        return 0

    if args.list_criteria:
        print("Speed: time to first content token, generation tok/s, wall time. Short prompt only.")
        print("Memory: RSS of the process listening on the endpoint port, if the OS reports it.")
        for task in TASKS:
            print(f"Task {task['id']} ({task['area']})")
        print("Not measured: long-context prefill, MMLU, or a single intelligence score.")
        return 0

    try:
        report = run_card(
            args.base_url,
            args.model,
            args.api_key,
            args.timeout,
            Path(args.out),
            args.skip_speed,
            args.skip_tasks,
        )
    except EndpointError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(to_markdown(report))
    print(f"Wrote {report['paths']['markdown']}")
    print(f"Wrote {report['paths']['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
