"""Auto-detect running model servers on this machine.

Three detection sources, in order of preference:

1. Port scan — probe each known port for an OpenAI-compatible /v1/models
   response. A response proves an engine is alive; no response means
   nothing is on that port (or a firewall is blocking us).

2. Binary scan — `pgrep` for known engine processes. Match a process
   to a port from its command line. Useful when a server is running on
   a non-default port.

3. Installed-app scan — look in /Applications and /usr/local/bin for
   engine apps that are installed but not running. The first-run
   onboarding panel uses this.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_model_card.engines import REGISTRY, EngineAdapter


# Default ports per engine family. Discovery probes these first.
DEFAULT_PORTS: list[tuple[str, int]] = [
    ("llamacpp", 18434),  # Hermes llama.cpp default
    ("llamacpp", 8080),   # standalone llama.cpp default
    ("omlx", 8000),
    ("ollama", 11434),
    ("lmstudio", 1234),
]

# Engine binary names to scan with pgrep.
ENGINE_BINARIES: dict[str, str] = {
    "llamacpp": "llama-server",
    "ollama": "ollama",
    "omlx": "omlx",
    "lmstudio": "LM Studio",
}


@dataclass
class DetectedEngine:
    family: str            # canonical id, e.g. "llamacpp"
    name: str              # human-readable
    url: str               # base URL with /v1
    port: int
    reachable: bool
    needs_auth: bool
    version: str | None
    detail: str = ""
    models: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "url": self.url,
            "port": self.port,
            "reachable": self.reachable,
            "needs_auth": self.needs_auth,
            "version": self.version,
            "detail": self.detail,
            "models": self.models,
        }


def probe_port(family: str, port: int, key: str | None = None) -> DetectedEngine:
    """Probe a single (family, port) pair."""
    adapter: EngineAdapter | None = REGISTRY.get(family)
    if adapter is None:
        return DetectedEngine(
            family=family, name=family, url=f"http://127.0.0.1:{port}/v1", port=port,
            reachable=False, needs_auth=False, version=None, detail=f"unknown engine: {family}",
        )

    url = f"http://127.0.0.1:{port}/v1"
    key_to_use = key
    if key_to_use is None and family == "llamacpp":
        # Auto-load Hermes key on probe.
        from open_model_card.engines.llamacpp import _hermes_key
        key_to_use = _hermes_key()
    if key_to_use is None and family == "omlx":
        # Auto-load oMLX key from ~/.omlx/settings.json.
        from open_model_card.engines.omlx import _omlx_key
        key_to_use = _omlx_key()

    p = adapter.probe(url, key_to_use)
    out = DetectedEngine(
        family=family,
        name=adapter.name,
        url=url,
        port=port,
        reachable=p.reachable,
        needs_auth=p.needs_auth,
        version=p.version,
        detail=p.detail,
    )
    if p.reachable and not p.needs_auth:
        try:
            ms = adapter.list_models(url, key_to_use)
            out.models = [
                {
                    "id": m.id,
                    "size_bytes": m.size_bytes,
                    "state": m.state,
                }
                for m in ms
            ]
        except Exception:
            pass
    return out


def scan_ports(extra: list[tuple[str, int]] | None = None, key: str | None = None) -> list[DetectedEngine]:
    """Probe every default (and any extra) port. Returns a list of all results."""
    ports = list(DEFAULT_PORTS)
    if extra:
        ports.extend(extra)
    seen: set[tuple[str, int]] = set()
    out: list[DetectedEngine] = []
    for family, port in ports:
        key_pair = (family, port)
        if key_pair in seen:
            continue
        seen.add(key_pair)
        out.append(probe_port(family, port, key=key))
    return out


def _parse_pgrep(line: str) -> tuple[int, str] | None:
    """Parse one pgrep -fl line into (pid, command) or None."""
    parts = line.strip().split(None, 1)
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    return int(parts[0]), parts[1]


def _port_in_command(command: str) -> int | None:
    """Find --port NNNN or -p NNNN in a process command line."""
    m = re.search(r"--port[=\s]+(\d+)", command)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:^|\s)-p\s*(\d+)(?:\s|$)", command)
    if m:
        return int(m.group(1))
    return None


def scan_binaries() -> list[tuple[str, int, str]]:
    """Look for known engine processes. Returns (family, port, command)."""
    if not shutil.which("pgrep"):
        return []
    out: list[tuple[str, int, str]] = []
    for family, binary in ENGINE_BINARIES.items():
        try:
            res = subprocess.run(["pgrep", "-fl", binary], capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in res.stdout.splitlines():
            parsed = _parse_pgrep(line)
            if not parsed:
                continue
            _pid, command = parsed
            port = _port_in_command(command) or DEFAULT_PORTS[[p[0] for p in DEFAULT_PORTS].index(family)][1] if family in [p[0] for p in DEFAULT_PORTS] else 0
            if port:
                out.append((family, port, command))
    return out


def scan_engines(extra: list[tuple[str, int]] | None = None, key: str | None = None) -> list[DetectedEngine]:
    """Full engine scan: ports + binaries, deduped by (family, port)."""
    results = scan_ports(extra=extra, key=key)
    seen = {(r.family, r.port) for r in results}
    for family, port, _cmd in scan_binaries():
        if (family, port) in seen:
            continue
        seen.add((family, port))
        results.append(probe_port(family, port, key=key))
    return results


# Installed-app scan — used by the first-run onboarding panel.

# Apps to look for in /Applications.
KNOWN_APP_BUNDLES: dict[str, str] = {
    "lmstudio": "LM Studio.app",
    "ollama": "Ollama.app",
}

# Binaries to look for in /usr/local/bin, /opt/homebrew/bin, /usr/bin.
KNOWN_BINARIES: dict[str, list[str]] = {
    "ollama": ["ollama"],
    "llamacpp": ["llama-server", "llama-cli"],
    "omlx": ["omlx"],
}


def scan_installed_apps() -> list[dict[str, Any]]:
    """List known engine apps that are installed on this Mac. Best-effort."""
    out: list[dict[str, Any]] = []
    if platform.system() != "Darwin":
        return out

    apps_dir = Path("/Applications")
    if apps_dir.is_dir():
        for family, app_name in KNOWN_APP_BUNDLES.items():
            app_path = apps_dir / app_name
            if app_path.is_dir():
                # Check Info.plist for version.
                plist = app_path / "Contents" / "Info.plist"
                version = None
                if plist.is_file():
                    try:
                        with plist.open("rb") as f:
                            info = plistlib.load(f)
                            version = info.get("CFBundleShortVersionString")
                    except (OSError, ValueError):
                        pass
                out.append({"family": family, "name": app_name, "path": str(app_path), "version": version, "kind": "app"})

    search_dirs = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"]
    for family, names in KNOWN_BINARIES.items():
        if any(r["family"] == family for r in out):
            continue
        for d in search_dirs:
            dp = Path(d)
            if not dp.is_dir():
                continue
            for binary in names:
                if (dp / binary).is_file():
                    out.append({"family": family, "name": binary, "path": str(dp / binary), "version": None, "kind": "binary"})
                    break
            if any(r["family"] == family for r in out):
                break

    return out
