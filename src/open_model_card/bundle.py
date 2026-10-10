"""Output bundle — the files written when the user runs Compare.

The bundle is what makes the card useful to the user's agent or
chatbot. Three files, each with a different audience:

  bundle.json        — machine-readable, for the user's agent
  bundle.short.md    — ≤500 tokens, fits in the agent's context window
  chat-brief.md      — chat-paste-ready, includes a suggested question

Plus the legacy `agent-brief.md` and `choice.md` are kept for
backward compatibility with v0.4 callers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from open_model_card.compare import recommend, comparison_markdown
from open_model_card.report import plain_summary
from open_model_card.schema import MACHINE_LOCAL, MODEL_PORTABLE, ENGINE_PORTABLE


def _machine_fingerprint(card: dict) -> dict:
    return card.get("machine") or {}


def _strip_pii(card: dict) -> dict:
    """Return a copy of the card with hostname-hash, paths, and SHA-256 removed."""
    import copy
    out = copy.deepcopy(card)
    if "machine" in out and "hostname_hash" in out["machine"]:
        out["machine"]["hostname_hash"] = None
    if "model" in out:
        for k in ("file_sha256", "path"):
            if k in out["model"]:
                out["model"][k] = None
    return out


def write_bundle(cards: list[dict], out_dir: Path, operator_notes: str = "", notes_filled: bool = False) -> dict:
    """Write the three bundle files. Returns the in-memory bundle for the UI."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Group cards by (engine_family, machine_fingerprint_hash) for cross-machine filtering.
    machine_groups: dict[str, list[dict]] = {}
    for c in cards:
        m = c.get("machine") or {}
        host = m.get("hostname_hash") or "unknown"
        machine_groups.setdefault(host, []).append(c)

    advice = recommend(cards)
    table = comparison_markdown(cards, advice)

    bundle = {
        "schema_version": "1.0",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "open-model-card",
        "card_count": len(cards),
        "machines": list(machine_groups.keys()),
        "operator_notes_filled": notes_filled,
        "operator_notes": operator_notes,
        "cards": cards,
        "recommendation": advice,
        "comparison_table": table,
    }

    bundle_path = out_dir / "bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    write_short(bundle, out_dir)
    write_chat_brief(bundle, out_dir)
    return bundle


def write_short(bundle: dict, out_dir: Path) -> None:
    """≤500 tokens. For the user's agent."""
    lines = [
        "# Brief — local model choice",
        "",
        f"{bundle['card_count']} cards from {len(bundle['machines'])} machine(s).",
        "",
        "## Recommendation",
        "",
    ]
    rec = bundle["recommendation"] or {}
    for job in ("transcripts", "operator", "cron"):
        choice = rec.get(job) or {}
        model = choice.get("model") or "none"
        engine = choice.get("engine") or ""
        label = f"{model} ({engine})" if engine and engine != "unknown:unknown" else model
        reason = choice.get("reason") or ""
        lines.append(f"- **{job}:** {label}. {reason}")
    paired = rec.get("do_not_pair") or []
    if paired:
        lines.append("")
        lines.append(f"Do not pair: {', '.join(paired)}.")
    if bundle.get("operator_notes_filled"):
        lines.append("")
        lines.append("## Operator notes")
        lines.append("")
        lines.append(bundle["operator_notes"][:1500])
    lines.append("")
    lines.append("## How to use this brief")
    lines.append("")
    lines.append("The full card data is in bundle.json. Compare table is in this file's `comparison_table` field. Recommend one model per job above; cite the operator's notes when explaining trade-offs.")
    (out_dir / "bundle.short.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_chat_brief(bundle: dict, out_dir: Path, strip_pii_flag: bool = False) -> None:
    """Chat-paste-ready brief. Includes a suggested question prompt."""
    cards = bundle["cards"]
    if strip_pii_flag:
        cards = [_strip_pii(c) for c in cards]

    def _model_id(c: dict) -> str:
        v1 = (c.get("model") or {}).get("id")
        if v1:
            return v1
        return str((c.get("endpoint") or {}).get("model") or "?")

    def _engine_name(c: dict) -> tuple[str, str]:
        e = c.get("engine") or {}
        name = e.get("name") or e.get("family") or "?"
        version = e.get("version") or "?"
        return name, version

    def _machine_str(c: dict) -> str:
        m = c.get("machine") or {}
        return f"{m.get('os', '?')}, {m.get('cpu', '?')}, {m.get('total_ram_mb', '?')} MB RAM"

    def _speed(c: dict) -> str:
        s = c.get("speed") or {}
        return f"{s.get('ttft_s', '?')}s first token · {s.get('tok_per_s', '?')} tok/s"

    def _memory(c: dict) -> str:
        m = c.get("memory") or {}
        return f"{m.get('rss_mb', '?')} MB resident"

    lines = [
        "## Question to ask",
        "",
        "Based on the cards below, which local model should I use for daily meeting",
        "transcripts on my machine? What about for cron jobs that need to be fast?",
        "If two models tie, say so. Don't invent a benchmark number.",
        "",
        "## Cards",
        "",
    ]
    for c in cards:
        name, version = _engine_name(c)
        model_id = _model_id(c)
        tasks = c.get("tasks") or []
        passed = sum(1 for t in tasks if t.get("pass"))
        lines.extend([
            f"### {model_id} on {name}",
            f"- Machine: {_machine_str(c)}",
            f"- Engine: {name} ({version}) on {(c.get('engine') or {}).get('url', '?') or (c.get('endpoint') or {}).get('base_url', '?')}",
            f"- Speed: {_speed(c)} · {_memory(c)}",
            f"- Tasks: {passed} of {len(tasks)} passed",
            "",
        ])

    lines.append("## My preferences (operator notes)")
    lines.append("")
    if bundle.get("operator_notes_filled"):
        lines.append(bundle["operator_notes"][:1500])
    else:
        lines.append("_(no operator notes filled in yet)_")
    lines.append("")
    (out_dir / "chat-brief.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_card(path: Path) -> dict:
    """Read a single card from disk. Forgiving about missing fields."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_cards(out_dir: Path) -> list[dict]:
    """Load all card JSONs in `out_dir`, sorted by creation time."""
    out: list[dict] = []
    for p in sorted(out_dir.glob("*.json")):
        if p.name in ("bundle.json", "choice.md"):
            continue
        if p.name.startswith("."):
            continue
        try:
            out.append(read_card(p))
        except (json.JSONDecodeError, OSError):
            continue
    return out
