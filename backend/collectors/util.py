"""Shared helpers for system collectors."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def run_cmd(args: list[str], timeout: float = 3.0) -> str | None:
    """Run a command; return stdout or None if unavailable/fails."""
    if not args or not shutil.which(args[0]):
        return None
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def bytes_to_gb(n: int | float | None, digits: int = 2) -> float | None:
    if n is None:
        return None
    return round(float(n) / (1024**3), digits)


def safe_dict(**kwargs: Any) -> dict[str, Any]:
    """Drop keys whose values are None for cleaner JSON."""
    return {k: v for k, v in kwargs.items() if v is not None}
