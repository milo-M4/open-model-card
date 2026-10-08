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
    args = parser.parse_args(argv)

    if args.compare:
        from open_model_card.compare import comparison_markdown, load_reports, recommend

        folder = Path(args.compare)
        reports = load_reports(folder)
        advice = recommend(reports)
        text = comparison_markdown(reports, advice)
        out = folder / "choice.md"
        out.write_text(text, encoding="utf-8")
        print(text)
        print(f"Wrote {out}")
        return 0 if reports else 2

    if args.list_criteria:
        print("Speed: time to first content token, generation tok/s, wall time. Short prompt only.")
        print("Memory: RSS of the process listening on the endpoint port, if the OS reports it.")
        for task in TASKS:
            print(f"Task {task['id']} ({task['area']})")
        print("Not measured: long-context prefill, MMLU, or a single intelligence score.")
        return 0

    try:
        model = args.model or (list_models(args.base_url, args.api_key, args.timeout) or [""])[0]
        if not model:
            print("No model id. Pass --model.", file=sys.stderr)
            return 2
        speed = None if args.skip_speed else stream_speed(args.base_url, model, args.api_key, args.timeout)
        rows = []
        if not args.skip_tasks:
            for task in TASKS:
                result = complete(args.base_url, model, task["prompt"], args.api_key, args.timeout)
                rows.append(score_task(task, result["text"]))
    except EndpointError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    port = urlparse(args.base_url).port or 80
    memory = rss_mb_for_port(port)
    report = build_report(
        {"base_url": args.base_url, "model": model},
        speed,
        rows,
        memory,
    )
    json_path, md_path = write_report(report, Path(args.out))
    print(to_markdown(report))
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
