"""Shared helpers for system collectors."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_hwmon_lock = threading.Lock()
_hwmon_temps: dict | None = None
_hwmon_at: float = 0.0
# One hwmon pass per live tick — cpu + gpu fallback used to scan twice.
HWMON_TEMPS_TTL = 0.25


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


def sensors_temperatures() -> dict:
    """Cached psutil hwmon read so one tick does not walk sysfs twice."""
    global _hwmon_temps, _hwmon_at
    now = time.monotonic()
    with _hwmon_lock:
        if _hwmon_temps is not None and (now - _hwmon_at) < HWMON_TEMPS_TTL:
            return _hwmon_temps
        try:
            import psutil

            _hwmon_temps = psutil.sensors_temperatures(fahrenheit=False) or {}
        except Exception:
            _hwmon_temps = {}
        _hwmon_at = now
        return _hwmon_temps


def reset_sensors_cache_for_tests() -> None:
    global _hwmon_temps, _hwmon_at
    with _hwmon_lock:
        _hwmon_temps = None
        _hwmon_at = 0.0
