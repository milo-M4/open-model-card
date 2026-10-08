"""Host memory snapshot. Best effort. Missing tools do not fail the run."""

from __future__ import annotations

import platform
import shutil
import subprocess


def rss_mb_for_port(port: int) -> dict:
    if not shutil.which("lsof") or not shutil.which("ps"):
        return {"available": False, "reason": "lsof or ps not on PATH"}
    try:
        listed = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": str(exc)}
    pids = [line.strip() for line in listed.stdout.splitlines() if line.strip().isdigit()]
    if not pids:
        return {"available": False, "reason": f"nothing listening on {port}"}
    total_kb = 0
    for pid in pids:
        probed = subprocess.run(
            ["ps", "-p", pid, "-o", "rss="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        rss = probed.stdout.strip()
        if rss.isdigit():
            total_kb += int(rss)
    return {
        "available": True,
        "pids": pids,
        "rss_mb": round(total_kb / 1024, 1),
        "platform": platform.platform(),
    }
