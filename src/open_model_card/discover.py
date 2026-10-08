"""Find model files. Listing is not loading."""

from __future__ import annotations

from pathlib import Path

EXTENSIONS = {".gguf", ".bin"}
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__"}


def search_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".hermes" / "models",
        home / ".ollama" / "models",
        home / ".omlx" / "models",
        home / "models",
    ]


def find_model_files(limit: int = 40) -> list[str]:
    found: list[str] = []
    for root in search_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if any(part in SKIP for part in path.parts):
                continue
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                found.append(str(path))
            if len(found) >= limit:
                return found
    return found
