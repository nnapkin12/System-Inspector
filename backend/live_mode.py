"""
Which queries belong in the live board vs a one-shot print.

Live-worthy: sensors that change (cpu, gpu, ram, temps, …).
Snapshot: facts (os, board, display, scan) and expensive / external net slices.
"""

from __future__ import annotations

from backend.fields import NET_DETAIL_FIELDS
from backend.query import parse_query

# Refresh these on a TTY unless the user asked for a snapshot.
LIVE_RESOURCES = frozenset(
    {
        "status",
        "cpu",
        "gpu",
        "memory",
        "temps",
        "fans",
        "disk",
        "net",
        "battery",
    }
)

# Print once. `si live os` still works if someone asks.
SNAPSHOT_RESOURCES = frozenset(
    {
        "board",
        "display",
        "os",
        "scan",
        "uptime",
        "version",
        "all",
    }
)

# Tables / HTTPS — not a meter board. Bare `si net` (throughput) stays live.
SNAPSHOT_NET_FIELDS = frozenset(NET_DETAIL_FIELDS)


def query_is_liveable(tokens: list[str]) -> bool:
    """True when every resource in the query is worth refreshing."""
    resources, fields, _unknown = parse_query(tokens)
    if not resources:
        return False
    if any(r in SNAPSHOT_RESOURCES for r in resources):
        return False
    if not all(r in LIVE_RESOURCES for r in resources):
        return False
    if "net" in resources and fields & SNAPSHOT_NET_FIELDS:
        return False
    return True


def should_enter_live(
    tokens: list[str],
    *,
    force_live: bool = False,
    once: bool = False,
    json_mode: bool = False,
    plain: bool = False,
    stdin_tty: bool = False,
    stdout_tty: bool = False,
) -> bool:
    """
    Decide whether this invocation opens the refresh loop.

    --once / --json → snapshot (si live gpu --json still streams).
    --plain → snapshot unless they typed `live`.
    Non-TTY → snapshot unless they typed `live`.
    """
    if once:
        return False
    if json_mode and not force_live:
        return False
    if force_live:
        return True
    if plain:
        return False
    if not (stdin_tty and stdout_tty):
        return False
    return query_is_liveable(tokens)
