"""Card retention — keep the last N cards per (engine, model), archive older.

`enforce` moves the overflow into `archive/<engine>/<model>/`. The card
JSON and Markdown are moved together so a card's two files never get
separated. The bundle.json, bundle.short.md, chat-brief.md, and
jobs/ files are not touched.
"""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path


# A card filename looks like: 20261009T192519Z-llamacpp-Qwen3.6-35B-A3B-UD-Q4_K_M.json
# The first segment is the timestamp, the rest is engine and model.
_CARD_PATTERN = re.compile(
    r"^(?P<stamp>\d{8}T\d{6}Z)-(?P<engine>[A-Za-z0-9._-]+)-(?P<model>.+?)(?P<ext>\.json|\.md)$"
)


def card_paths(out_dir: Path) -> list[Path]:
    """All card JSON and Markdown files in `out_dir` (no bundle/jobs)."""
    out: list[Path] = []
    if not out_dir.is_dir():
        return out
    for p in out_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix not in (".json", ".md"):
            continue
        m = _CARD_PATTERN.match(p.name)
        if not m:
            continue
        if p.name in ("bundle.json", "operator.md", "agent-brief.md", "choice.md"):
            continue
        out.append(p)
    return out


def _group_key(p: Path) -> tuple[str, str]:
    m = _CARD_PATTERN.match(p.name)
    if not m:
        return ("", "")
    return (m.group("engine"), m.group("model"))


def _stamp(p: Path) -> str:
    m = _CARD_PATTERN.match(p.name)
    return m.group("stamp") if m else ""


def enforce(out_dir: Path, keep: int = 10) -> int:
    """Move older cards into `archive/`. Returns the number of files moved.

    `keep` is the number of CARDS (each card is a .json + .md pair) to
    keep per (engine, model). The newest N stamps are kept; older
    stamps are moved to `archive/<engine>/<model>/`.
    """
    moved = 0
    if not out_dir.is_dir():
        return 0
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for p in card_paths(out_dir):
        groups[_group_key(p)].append(p)
    for (engine, model), paths in groups.items():
        # Newest first by timestamp.
        paths.sort(key=_stamp, reverse=True)
        # Group by stamp; keep the `keep` newest stamps.
        seen_stamps: set[str] = set()
        keep_stamps: set[str] = set()
        for p in paths:
            s = _stamp(p)
            if s in seen_stamps:
                continue
            seen_stamps.add(s)
            if len(keep_stamps) < keep:
                keep_stamps.add(s)
        for p in paths:
            s = _stamp(p)
            if s in keep_stamps:
                continue
            archive_dir = out_dir / "archive" / engine / model
            archive_dir.mkdir(parents=True, exist_ok=True)
            target = archive_dir / p.name
            shutil.move(str(p), str(target))
            moved += 1
    return moved
