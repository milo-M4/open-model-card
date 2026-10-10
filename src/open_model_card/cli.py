"""Command line. v1.0 — runs the card and writes the bundle on compare."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from open_model_card.client import EndpointError, complete, stream_speed, unload_model
from open_model_card.engines import REGISTRY
from open_model_card.engines import get as get_adapter
from open_model_card.hostmem import rss_mb_for_port
from open_model_card.report import (
    build_report,
    engine_fingerprint,
    model_fingerprint,
    to_markdown,
    write_report,
)
from open_model_card.score import score_task
from open_model_card.tasks import TASKS


def run_card(
    base_url: str,
    model: str,
    api_key: str,
    timeout: float,
    out: Path,
    skip_speed: bool,
    skip_tasks: bool,
    progress=None,
    thinking_aware: bool = False,
    engine_family: str | None = None,
) -> dict:
    def note(message: str) -> None:
        if progress:
            progress(message)

    # Pick the right adapter for this URL.
    family = engine_family or _guess_family(base_url)
    adapter = get_adapter(family) if family else None

    note("Asking the server which model to test")
    if not model and adapter is not None:
        try:
            ms = adapter.list_models(base_url, api_key, timeout)
            model = ms[0].id if ms else ""
        except Exception:
            model = ""
    if not model:
        raise EndpointError("No model id. Pass a model name.")

    # Engine version, if available.
    engine_version = None
    if adapter is not None:
        try:
            p = adapter.probe(base_url, api_key, 5.0)
            engine_version = p.version
        except Exception:
            pass

    # Model size for the fingerprint.
    size_bytes = None
    if adapter is not None and hasattr(adapter, "model_size"):
        try:
            size_bytes = adapter.model_size(base_url, model, api_key, 10.0)
        except Exception:
            pass

    speed = None
    if not skip_speed:
        note("Measuring how fast a short reply starts and finishes")
        speed = stream_speed(base_url, model, api_key, timeout)

    rows = []
    if not skip_tasks:
        for task in TASKS:
            note(f"Checking {task['area']}")
            result = complete(base_url, model, task["prompt"], api_key, timeout)
            rows.append(score_task(task, result["text"], thinking_aware))

    port = urlparse(base_url).port or 80
    machine = None  # build_report fills this
    engine = engine_fingerprint(
        family=family,
        name=adapter.name if adapter else family,
        url=base_url,
        version=engine_version,
        auth=("hermes-key" if _is_hermes_engine(family) and api_key else ("key" if api_key else "none")),
    )
    model_fp = model_fingerprint(model_id=model, size_bytes=size_bytes)
    report = build_report(
        {"base_url": base_url, "model": model, "family": family, "engine_name": engine["name"], "engine_version": engine_version},
        speed, rows, rss_mb_for_port(port),
        engine=engine, model=model_fp,
    )
    report["thinking_aware"] = thinking_aware
    note("Unloading the model so another test can start")
    if adapter is not None and hasattr(adapter, "unload"):
        try:
            u = adapter.unload(base_url, model, api_key, timeout)
            report["unload"] = {"attempted": u.attempted, "unloaded": u.unloaded, "detail": u.detail}
        except Exception as exc:
            report["unload"] = {"attempted": False, "unloaded": False, "detail": str(exc)}
    else:
        # Fallback to the legacy client helper.
        report["unload"] = unload_model(base_url, model, api_key)
    json_path, md_path = write_report(report, out)
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report


def _guess_family(base_url: str) -> str:
    """Pick an adapter family from the URL if the caller did not pass one."""
    try:
        port = urlparse(base_url).port
    except Exception:
        return "llamacpp"
    return {
        18434: "llamacpp",
        11434: "ollama",
        8000: "omlx",
        1234: "lmstudio",
        8080: "llamacpp",
    }.get(port, "llamacpp")


def _is_hermes_engine(family: str) -> bool:
    """True when this engine is the Hermes-managed llama.cpp server.

    Hermes stores its API key in
    ~/.hermes/runtimes/llamacpp/server.json, and the server runs on
    port 18434. We treat that combination as the Hermes engine.
    """
    if family != "llamacpp":
        return False
    p = Path.home() / ".hermes" / "runtimes" / "llamacpp" / "server.json"
    return p.is_file()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a repeatable report card for a local OpenAI-compatible model."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:18434/v1")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--engine", default="", help="Engine family: llamacpp / ollama / omlx / lmstudio. Auto-detected from URL if not given.")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--out", default="reports")
    parser.add_argument("--skip-speed", action="store_true")
    parser.add_argument("--skip-tasks", action="store_true")
    parser.add_argument(
        "--thinking-aware",
        action="store_true",
        help="For a thinking model, grade strict format tests on the part of the reply "
             "that looks like a final answer, not on the whole reasoning trace.",
    )
    parser.add_argument("--list-criteria", action="store_true")
    parser.add_argument("--compare", default="", help="Directory of report JSON files to rank")
    parser.add_argument("--profile", default="", help="Operator notes markdown to include in the agent brief")
    parser.add_argument("--ui", action="store_true", help="Open a local page to pick a model, run, and compare")
    parser.add_argument("--ui-port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.compare:
        from open_model_card.brief import agent_brief, read_operator_notes
        from open_model_card.bundle import load_cards, write_bundle
        from open_model_card.compare import recommend, comparison_markdown

        folder = Path(args.compare)
        cards = load_cards(folder)
        advice = recommend(cards)
        text = comparison_markdown(cards, advice)
        # Legacy files for v0.4 callers.
        (folder / "choice.md").write_text(text, encoding="utf-8")
        profile = Path(args.profile) if args.profile else folder / "operator.md"
        notes, filled = read_operator_notes(profile if profile.is_file() else None)
        (folder / "agent-brief.md").write_text(agent_brief(text, notes, filled), encoding="utf-8")
        # v1.0 bundle.
        write_bundle(cards, folder, notes, filled)
        print(text)
        print(f"Wrote {folder / 'choice.md'}")
        print(f"Wrote {folder / 'agent-brief.md'}")
        print(f"Wrote {folder / 'bundle.json'}")
        print(f"Wrote {folder / 'bundle.short.md'}")
        print(f"Wrote {folder / 'chat-brief.md'}")
        return 0 if cards else 2

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
            thinking_aware=args.thinking_aware,
            engine_family=args.engine or None,
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
