"""
What people type → resources and field filters.

``si gpu temp`` is one GPU payload with a temp filter — not a separate route.
Resource handlers live in ``resources.py``.
"""

from __future__ import annotations

from backend.collectors.vitals import VITALS_ALL
from backend.fields import NET_FIELD_ALIASES, OS_DETAIL_FIELDS

CANONICAL = (
    "status",
    "cpu",
    "gpu",
    "memory",
    "temps",
    "fans",
    "board",
    "os",
    "disk",
    "net",
    "battery",
    "scan",
    "uptime",
    "version",
    "all",
)

# What people type → canonical resource
ALIASES: dict[str, str] = {
    "status": "status",
    "summary": "status",
    "cpu": "cpu",
    "processor": "cpu",
    "gpu": "gpu",
    "graphics": "gpu",
    "nvidia": "gpu",
    "vram": "gpu",
    "ram": "memory",
    "memory": "memory",
    "mem": "memory",
    "temp": "temps",
    "temps": "temps",
    "temperature": "temps",
    "temperatures": "temps",
    "thermal": "temps",
    "board": "board",
    "motherboard": "board",
    "mb": "board",
    "mobo": "board",
    "mainboard": "board",
    "os": "os",
    "system": "os",
    # "host" = full OS block; use field "hostname" for the host name only
    "host": "os",
    "disk": "disk",
    "storage": "disk",
    "ssd": "disk",
    "hdd": "disk",
    "drive": "disk",
    "net": "net",
    "network": "net",
    "eth": "net",
    "battery": "battery",
    "bat": "battery",
    "power": "battery",
    "fans": "fans",
    "fan": "fans",
    "cooling": "fans",
    "scan": "scan",
    "inventory": "scan",
    "hw": "scan",
    "hardware": "scan",
    "uptime": "uptime",
    "up": "uptime",
    # bare "version" / "ver" → this app, not the OS
    "version": "version",
    "ver": "version",
    "about": "version",
    "all": "all",
    "everything": "all",
    "full": "all",
}

# Live vitals domains each resource actually reads (unioned for bundles).
_RESOURCE_VITALS: dict[str, frozenset[str]] = {
    "status": frozenset({"cpu", "memory", "gpus"}),
    "cpu": frozenset({"cpu"}),
    "gpu": frozenset({"gpus"}),
    "memory": frozenset({"memory"}),
    "temps": frozenset({"cpu", "gpus", "temperatures"}),
    "fans": frozenset({"fans", "gpus"}),
    "disk": frozenset({"storage", "rates"}),
    "net": frozenset({"network", "rates"}),
    "battery": frozenset({"battery"}),
    "uptime": frozenset({"boot_time"}),
}

# Optional field tokens (with a resource, or alone for a few shortcuts)
FIELD_ALIASES: dict[str, str] = {
    "temp": "temp",
    "temps": "temp",
    "temperature": "temp",
    "usage": "usage",
    "util": "usage",
    "load": "usage",
    "name": "name",
    "model": "name",
    "summary": "summary",
    # OS slices — "si kernel" or "si os kernel"
    "kernel": "kernel",
    "hostname": "hostname",
    "desktop": "desktop",
    "de": "desktop",
    "arch": "arch",
    "architecture": "arch",
    "distro": "version",
    "release": "version",
}


def vitals_needs_for(resources: list[str]) -> frozenset[str]:
    """Minimal vitals domains for a live query — avoids full get_vitals() every tick."""
    needs: set[str] = set()
    for r in resources:
        needs.update(_RESOURCE_VITALS.get(r, ()))
    return frozenset(needs) if needs else VITALS_ALL


def vitals_needs_for_tokens(tokens: list[str]) -> frozenset[str]:
    resources, _fields, _unknown = parse_query(tokens)
    return vitals_needs_for(resources)


def is_known_token(token: str) -> bool:
    t = token.strip().lower()
    return t in ALIASES or t in FIELD_ALIASES or t in NET_FIELD_ALIASES


def resolve_token(token: str) -> tuple[str | None, str | None]:
    """Return (resource|None, field|None) for one word (simple cases)."""
    t = token.strip().lower()
    if not t:
        return None, None
    if t in FIELD_ALIASES:
        return None, FIELD_ALIASES[t]
    if t in ALIASES:
        return ALIASES[t], None
    return None, None


def parse_query(tokens: list[str]) -> tuple[list[str], set[str], list[str]]:
    """
    Parse freeform tokens into (resources, fields, unknown).

      si kernel           → os + field kernel
      si os version       → os + field version
      si version          → app version
      si temp             → temps resource
    """
    raw_tokens = [t.strip() for t in tokens if t and t.strip()]
    lower = [t.lower() for t in raw_tokens]

    os_context = any(ALIASES.get(t) == "os" or t in ("os", "system") for t in lower)

    resources: list[str] = []
    fields: set[str] = set()
    unknown: list[str] = []
    seen: set[str] = set()

    for t in lower:
        if t in ("version", "ver"):
            if os_context:
                fields.add("version")
            elif "version" not in seen:
                resources.append("version")
                seen.add("version")
            continue

        if t in NET_FIELD_ALIASES:
            fields.add(NET_FIELD_ALIASES[t])
            if "net" not in seen:
                resources.append("net")
                seen.add("net")
            continue

        res, field = resolve_token(t)
        if field:
            fields.add(field)
            continue
        if res:
            if res not in seen:
                resources.append(res)
                seen.add(res)
            continue
        unknown.append(t)

    if not resources and "temp" in fields:
        resources = ["temps"]
        fields.discard("temp")

    if not resources and fields & OS_DETAIL_FIELDS:
        resources = ["os"]

    if not resources and fields:
        resources = ["status"]

    return resources, fields, unknown
