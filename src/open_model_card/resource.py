"""System resource state — RAM, memory pressure, top consumers.

This is the macOS-first version. Other OSes return "unavailable" with a
clear reason. The values here feed the SYSTEM region of the UI and the
resource-guard decisions before each test.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class SystemState:
    """A snapshot of the machine's resource state."""

    available: bool
    total_ram_mb: float | None = None
    free_ram_mb: float | None = None
    pressure: str = "unknown"  # "normal" / "warn" / "critical" / "unknown"
    swap_used_mb: float | None = None
    reason: str = ""
    platform: str = platform.platform()


def _run(cmd: list[str], timeout: float = 5.0) -> tuple[int, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return out.returncode, (out.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _sysctl_int(name: str) -> int | None:
    code, out = _run(["sysctl", "-n", name])
    if code != 0 or not out.isdigit():
        return None
    return int(out)


def _vm_stat_free_mb() -> int | None:
    code, out = _run(["vm_stat"])
    if code != 0:
        return None
    page_size = 4096  # Apple ARM
    free = 0
    for line in out.splitlines():
        if "Pages free" in line or "Pages inactive" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                free += int(digits)
    return round(free * page_size / (1024 * 1024), 1) if free else None


def collect() -> SystemState:
    """Snapshot the current machine state."""
    if not shutil.which("sysctl"):
        return SystemState(available=False, reason="sysctl not on PATH")

    total_mb = _sysctl_int("hw.memsize")
    if total_mb is not None:
        total_mb = round(total_mb / (1024 * 1024), 1)
    free_mb = _vm_stat_free_mb()

    pressure_raw = _sysctl_int("kern.memorystatus_vm_pressure_level")
    pressure = _pressure_label(pressure_raw)

    swap_used = None
    code, out = _run(["sysctl", "vm.swapusage"])
    if code == 0 and "used = " in out:
        # "used = 1234M" — parse it.
        try:
            chunk = out.split("used = ", 1)[1].split(",")[0].strip()
            if chunk.endswith("M"):
                swap_used = int(chunk[:-1])
            elif chunk.endswith("G"):
                swap_used = int(float(chunk[:-1]) * 1024)
            elif chunk.endswith("K"):
                swap_used = round(int(chunk[:-1]) / 1024, 1)
        except (ValueError, IndexError):
            pass

    if total_mb is None and free_mb is None:
        return SystemState(available=False, reason="could not read memory sizes")

    return SystemState(
        available=True,
        total_ram_mb=total_mb,
        free_ram_mb=free_mb,
        pressure=pressure,
        swap_used_mb=swap_used,
    )


def _pressure_label(level: int | None) -> str:
    """Translate the kern.memorystatus_vm_pressure_level integer to a label.

    Levels (from xnu/osfmk/kern/memorystatus.c):
        1 — normal
        2 — warning
        4 — critical
    """
    if level is None:
        return "unknown"
    if level >= 4:
        return "critical"
    if level >= 2:
        return "warn"
    return "normal"


def top_consumers(limit: int = 5) -> list[dict]:
    """List the top RSS-using user processes. Best-effort."""
    if not shutil.which("ps"):
        return []
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,rss=,comm=", "-r"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[dict] = []
    for line in out.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        rows.append({"pid": int(parts[0]), "rss_mb": round(int(parts[1]) / 1024, 1), "name": parts[2]})
        if len(rows) >= limit:
            break
    return rows
