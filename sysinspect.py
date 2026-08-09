"""
System Inspector CLI — short commands like: gpu · cpu temp · motherboard

Primary name: sysinspect
Also works as:        si   (wrapper script)

Does not require the web server. Calls collectors / resources directly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.resources import (  # noqa: E402
    format_human,
    list_commands_help,
    run_query,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(list_commands_help())
        return 0

    parser = argparse.ArgumentParser(
        prog="sysinspect",
        description="System Inspector CLI — short hardware & vitals queries",
        add_help=False,
    )
    parser.add_argument("tokens", nargs="*", help="resource and optional field words")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--pci", action="store_true", help="Include PCI list for scan")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Watch interval seconds (default 1)",
    )
    parser.add_argument("--help", "-h", action="store_true")

    # watch is a special first token handled manually for nicer UX
    watch = False
    if argv and argv[0].lower() == "watch":
        watch = True
        argv = argv[1:]

    args, unknown = parser.parse_known_args(argv)
    if args.help:
        print(list_commands_help())
        return 0

    tokens = list(args.tokens) + list(unknown)
    # strip flags that landed in unknown poorly
    tokens = [t for t in tokens if not t.startswith("-")]

    if not tokens:
        print(list_commands_help())
        return 0

    def once() -> int:
        payload = run_query(tokens, include_pci=args.pci)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(format_human(payload))
        return 0 if payload.get("ok") else 1

    if not watch:
        return once()

    # watch loop
    try:
        while True:
            if not args.json:
                # clear-ish screen without clearing scrollback harshly
                print("\033[2J\033[H", end="")
                print(f"sysinspect watch {' '.join(tokens)}  ·  every {args.interval}s  ·  Ctrl+C stop\n")
            payload = run_query(tokens, include_pci=args.pci)
            if args.json:
                print(json.dumps(payload))
            else:
                print(format_human(payload))
            if not payload.get("ok") and args.json:
                return 1
            time.sleep(max(args.interval, 0.2))
    except KeyboardInterrupt:
        if not args.json:
            print("\nstopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
