"""Card writer — JSON + Markdown.

A v1 card has these top-level sections:

  schema_version    — "1.0"
  tool              — "open-model-card"
  created           — UTC ISO timestamp
  machine           — fingerprint (OS, arch, total RAM, CPU, GPU, hostname-hash)
  engine            — fingerprint (name, version, url, auth method)
  model             — fingerprint (id, file_sha256, size_bytes)
  speed             — ttft, tok/s, etc. comparability="machine-local"
  memory            — listener RSS, etc. comparability="machine-local"
  tasks             — the 12 fixed tests, each with comparability="model-portable"
  areas             — per-area pass counts
  strengths         — best/weak areas
  thinking_aware    — bool
  limits            — list of caveats
  unload            — engine-side unload result

v0.4 cards (which lack machine/engine/model fingerprints) are still
readable — the comparability filter treats missing fields as machine-
local by default. The loader does not break.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

from open_model_card.score import area_summary, strengths
from open_model_card.schema import (
    SCHEMA_VERSION,
    MACHINE_LOCAL,
    MODEL_PORTABLE,
    speed_verdict,
)


def machine_fingerprint() -> dict:
    """Snapshot the machine. Called once per card run."""
    hostname_hash = "sha256:" + hashlib.sha256(socket.gethostname().encode()).hexdigest()[:16]
    try:
        import subprocess
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=2, check=False)
        total_ram_mb = round(int(out.stdout.strip()) / (1024 * 1024), 1) if out.returncode == 0 and out.stdout.strip().isdigit() else None
    except Exception:
        total_ram_mb = None
    return {
        "os": platform.platform(),
        "arch": platform.machine(),
        "total_ram_mb": total_ram_mb,
        "cpu": platform.processor() or None,
        "gpu": None,
        "hostname_hash": hostname_hash,
    }


def engine_fingerprint(family: str, name: str, url: str, version: str | None, auth: str | None) -> dict:
    return {
        "name": name,
        "family": family,
        "version": version,
        "url": url,
        "auth": auth or "none",
    }


def model_fingerprint(model_id: str, file_path: str | None = None, size_bytes: int | None = None) -> dict:
    sha = None
    if file_path:
        try:
            sha = "sha256:" + hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        except OSError:
            pass
    return {
        "id": model_id,
        "file_sha256": sha,
        "path": file_path,
        "size_bytes": size_bytes,
    }


def build_report(
    meta: dict,
    speed: dict | None,
    tasks: list[dict],
    memory: dict,
    machine: dict | None = None,
    engine: dict | None = None,
    model: dict | None = None,
) -> dict:
    """Assemble a v1 card from the run data.

    `meta` is the legacy v0.4 shape: {"base_url", "model"}. The v1
    fields (machine/engine/model fingerprints) are filled in by the
    caller when known, or computed here when not.
    """
    machine = machine or machine_fingerprint()
    engine = engine or engine_fingerprint(
        family=meta.get("family", "unknown"),
        name=meta.get("engine_name", "unknown"),
        url=meta.get("base_url", ""),
        version=meta.get("engine_version"),
        auth=meta.get("auth"),
    )
    model = model or model_fingerprint(model_id=meta.get("model", ""))

    # Tag tasks with comparability.
    tagged_tasks = []
    for t in tasks or []:
        t_copy = dict(t)
        t_copy.setdefault("comparability", MODEL_PORTABLE)
        tagged_tasks.append(t_copy)

    # Tag speed and memory as machine-local.
    speed_copy = dict(speed) if speed else None
    if speed_copy is not None:
        speed_copy.setdefault("comparability", MACHINE_LOCAL)
    memory_copy = dict(memory) if memory else {}
    memory_copy.setdefault("comparability", MACHINE_LOCAL)

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "open-model-card",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": machine,
        "engine": engine,
        "model": model,
        "speed": speed_copy,
        "memory": memory_copy,
        "tasks": tagged_tasks,
        "areas": area_summary(tagged_tasks),
        "strengths": strengths(tagged_tasks),
        "limits": [
            "Short-prompt speed is not a long-context prefill number.",
            "Task passes are checks, not a general intelligence score.",
            "Memory is the listener process RSS when the OS reports it.",
        ],
    }


def _size_band_from_model_id(model_id: str) -> float | None:
    """Heuristic: extract parameter count (in billions) from a model name."""
    m = re.search(r"(?i)(\d+(?:\.\d+)?)\s*b\b", model_id)
    if m:
        return float(m.group(1))
    # "A3B" / "A1.5B" style (Qwen3 MoE).
    m = re.search(r"(?i)a(\d+(?:\.\d+)?)\s*b", model_id)
    if m:
        # Active parameters, not total.
        return float(m.group(1))
    return None


def plain_summary(report: dict, verdict_on: bool = True) -> str:
    """Sentences for a person. Verdict language is on by default."""
    model = (report.get("model") or {}).get("id") or "This model"
    engine = (report.get("engine") or {}).get("name") or ""
    speed = report.get("speed") or {}
    memory = report.get("memory") or {}
    tasks = report.get("tasks") or []
    thinking_aware = bool(report.get("thinking_aware"))
    passed = sum(1 for row in tasks if row.get("pass"))

    lines = [f"{model} on {engine} finished this test." if engine else f"{model} finished this test."]

    if thinking_aware:
        lines.append("Strict format tests were graded on the final answer, not the reasoning trace. The model was treated as a thinking model.")

    if speed.get("ttft_s") is not None:
        verdict = ""
        if verdict_on:
            band = _size_band_from_model_id(model)
            v = speed_verdict(speed.get("tok_per_s"), band)
            verdict = f" — {v} for this size" if v != "unknown" else ""
        lines.append(f"It started answering in {speed['ttft_s']} seconds{verdict}.")

    if speed.get("tok_per_s") is not None:
        lines.append(f"After that, it wrote about {speed['tok_per_s']} small word-pieces a second.")

    if memory.get("available") and memory.get("rss_mb") is not None:
        gb = float(memory["rss_mb"]) / 1024
        lines.append(f"The server was using about {gb:.1f} GB of memory.")
        if gb >= 20:
            lines.append("That is a large model. Do not run another large model at the same time.")

    if tasks:
        lines.append(f"It passed {passed} of {len(tasks)} small checks.")

    for row in tasks:
        verb = "did" if row.get("pass") else "did not"
        lines.append(f"It {verb} pass {row.get('area')}.")

    unload = report.get("unload") or {}
    if unload.get("unloaded"):
        lines.append("The model was unloaded when the test finished. You can test another one.")
    elif unload.get("attempted"):
        lines.append("The test finished, but this server did not unload the model. Do not start another large model until this one is gone.")

    lines.append("The technical record is below. You can skip it if these sentences are enough.")
    return "\n".join(lines)


def to_markdown(report: dict) -> str:
    """Human-readable card. Engine + machine fingerprints appear at the top."""
    model = (report.get("model") or {}).get("id") or "?"
    engine = (report.get("engine") or {}).get("name") or "?"
    machine = report.get("machine") or {}
    lines = [
        f"# Model card — {model}",
        "",
        f"- Engine: {engine} `{(report.get('engine') or {}).get('url', '?')}`",
        f"- Machine: {machine.get('os', '?')}, {machine.get('arch', '?')}, {machine.get('total_ram_mb', '?')} MB RAM",
        f"- Created: {report.get('created', '?')}",
        f"- Schema: v{report.get('schema_version', '?')}",
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
    if report.get("thinking_aware"):
        lines.extend([
            "",
            "## Thinking model",
            "",
            "This card was run with thinking-aware scoring. The model prints a "
            "reasoning trace before its final answer. Strict format tests were "
            "graded on the part of the reply that looks like a final answer.",
            "",
        ])
    lines.extend(["", "## Tasks", ""])
    lines.append("| Task | Area | Result | Detail |")
    lines.append("|---|---|---|---|")
    for row in report.get("tasks") or []:
        mark = "pass" if row["pass"] else "fail"
        detail = str(row["detail"]).replace("|", "/")
        lines.append(f"| {row['id']} | {row['area']} | {mark} | {detail} |")
    found = report.get("strengths") or {}
    lines.extend([
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
    ])
    for item in report.get("limits") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _safe_stem(s: str) -> str:
    """Strip characters that don't belong in a filename."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")


def write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    """Write a card to disk. Filename includes engine family and model id."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["created"].replace(":", "").replace("-", "")
    engine_family = (report.get("engine") or {}).get("family") or "engine"
    model_id = (report.get("model") or {}).get("id") or "model"
    stem = f"{stamp}-{_safe_stem(engine_family)}-{_safe_stem(model_id)}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, md_path
