from __future__ import annotations

import platform
import socket
from pathlib import Path

from .util import read_text, run_cmd, safe_dict


def collect_os() -> dict:
    pretty = None
    os_release: dict[str, str] = {}
    path = Path("/etc/os-release")
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            os_release[key] = value.strip().strip('"')
        pretty = os_release.get("PRETTY_NAME")

    uname = platform.uname()
    hostname = socket.gethostname()
    desktop = (
        __import__("os").environ.get("XDG_CURRENT_DESKTOP")
        or __import__("os").environ.get("DESKTOP_SESSION")
    )
    session_type = __import__("os").environ.get("XDG_SESSION_TYPE")

    return safe_dict(
        category="os",
        name=pretty or f"{uname.system} {uname.release}",
        system=uname.system,
        release=uname.release,
        version=uname.version,
        machine=uname.machine,
        hostname=hostname,
        pretty_name=pretty,
        id=os_release.get("ID"),
        id_like=os_release.get("ID_LIKE"),
        version_id=os_release.get("VERSION_ID"),
        desktop_environment=desktop,
        session_type=session_type,
        kernel=uname.release,
        architecture=platform.machine(),
        python=platform.python_version(),
        boot_id=read_text("/proc/sys/kernel/random/boot_id"),
        uptime_seconds=_uptime_seconds(),
        raw_os_release=os_release or None,
    )


def _uptime_seconds() -> float | None:
    raw = read_text("/proc/uptime")
    if not raw:
        return None
    try:
        return float(raw.split()[0])
    except (IndexError, ValueError):
        return None
