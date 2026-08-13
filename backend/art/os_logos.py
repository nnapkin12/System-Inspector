"""
Distro ASCII logos — uses fastfetch when installed (400+ logos, MIT license).

https://github.com/fastfetch-cli/fastfetch

Falls back to a tiny generic logo if fastfetch is missing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache

# os-release ID → fastfetch built-in logo name
_ID_TO_FF: dict[str, str] = {
    "pop": "pop",
    "pop-os": "pop",
    "ubuntu": "ubuntu",
    "debian": "debian",
    "fedora": "fedora",
    "arch": "arch",
    "manjaro": "manjaro",
    "nixos": "nixos",
    "opensuse-tumbleweed": "opensuse",
    "opensuse-leap": "opensuse",
    "opensuse": "opensuse",
    "linuxmint": "linuxmint",
    "mint": "linuxmint",
    "elementary": "elementary",
    "endeavouros": "endeavouros",
    "rocky": "rockylinux",
    "rockylinux": "rockylinux",
    "almalinux": "almalinux",
    "centos": "centos",
    "alpine": "alpine",
    "gentoo": "gentoo",
    "kali": "kali",
    "zorin": "zorin",
    "neon": "neon",
    "steamdeck": "steamdeck",
    "bazzite": "bazzite",
    "windows": "windows",
    "darwin": "macos",
}

_FALLBACK: dict[str, list[str]] = {
    "linux": [
        "  .---.",
        "  |   |",
        "  |___|",
        "  Linux",
    ],
}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


@lru_cache(maxsize=1)
def _fastfetch_logo_names() -> frozenset[str]:
    if not shutil.which("fastfetch"):
        return frozenset()
    try:
        proc = subprocess.run(
            ["fastfetch", "--list-logos"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    names: set[str] = set()
    for line in proc.stdout.splitlines():
        for match in re.finditer(r'"([^"]+)"', line):
            names.add(match.group(1).lower())
    return frozenset(names)


@lru_cache(maxsize=128)
def _fastfetch_logo(name: str) -> tuple[str, ...] | None:
    key = name.lower()
    if key not in _fastfetch_logo_names():
        return None
    try:
        proc = subprocess.run(
            ["fastfetch", "--logo", key, "--structure", "none", "--pipe"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = proc.stdout.rstrip("\n").split("\n")
    if not any(ln.strip() for ln in lines):
        return None
    return tuple(lines)


def _candidates(data: dict) -> list[str]:
    id_ = _norm(data.get("id"))
    id_like = [_norm(x) for x in (data.get("id_like") or "").replace(",", " ").split()]
    pretty = _norm(data.get("pretty_name") or data.get("name"))
    system = _norm(data.get("system"))

    out: list[str] = []

    def add(name: str) -> None:
        n = name.strip().lower()
        if n and n not in out:
            out.append(n)

    if id_ in _ID_TO_FF:
        add(_ID_TO_FF[id_])
    add(id_)
    for token in id_like:
        if token in _ID_TO_FF:
            add(_ID_TO_FF[token])
        add(token)
    if "pop" in id_ or "pop" in pretty:
        add("pop")
    if "ubuntu" in pretty:
        add("ubuntu")
    if "debian" in pretty or "debian" in id_like:
        add("debian")
    if "arch" in pretty:
        add("arch")
    if "fedora" in pretty:
        add("fedora")
    if "manjaro" in pretty:
        add("manjaro")
    if "nixos" in pretty:
        add("nixos")
    if "mint" in pretty:
        add("linuxmint")
    if system == "windows":
        add("windows")
    if system == "darwin":
        add("macos")
    add("linux")
    return out


def distro_logo(data: dict) -> tuple[str, list[str], bool]:
    """
    Return (distro_key, logo_lines, from_fastfetch).
    When from_fastfetch is True, lines may already include ANSI color codes.
    """
    for cand in _candidates(data):
        ff = _fastfetch_logo(cand)
        if ff:
            return cand, list(ff), True
    key = _candidates(data)[0] if _candidates(data) else "linux"
    return key, list(_FALLBACK.get(key, _FALLBACK["linux"])), False
