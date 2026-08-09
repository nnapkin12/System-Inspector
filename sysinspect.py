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
from backend.tui import (  # noqa: E402
    LiveHistory,
    banner,
    decorate_human,
    extract_plot_series,
    render_graph,
    short_banner,
    use_color,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    plain = "--plain" in argv or "-p" in argv
    argv = [a for a in argv if a not in ("--plain", "-p")]
    color = use_color(not plain)

    if not argv or argv[0] in ("-h", "--help", "help"):
        if not plain:
            print(banner(color=color, subtitle="type a resource · full list: COMMANDS.md / help below"))
            print()
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
    parser.add_argument("--no-graph", action="store_true", help="Watch mode without live graph")
    parser.add_argument("--help", "-h", action="store_true")

    watch = False
    if argv and argv[0].lower() in ("watch", "graph", "live"):
        watch = True
        argv = argv[1:]

    args, unknown = parser.parse_known_args(argv)
    if args.help:
        if not plain:
            print(banner(color=color))
            print()
        print(list_commands_help())
        return 0

    tokens = list(args.tokens) + list(unknown)
    tokens = [t for t in tokens if not t.startswith("-")]

    if not tokens:
        if not plain:
            print(banner(color=color))
            print()
        print(list_commands_help())
        return 0

    def render_once(payload: dict) -> str:
        if args.json:
            return json.dumps(payload, indent=2)
        body = format_human(payload)
        if not plain:
            body = decorate_human(body, color=color)
        return body

    def once() -> int:
        payload = run_query(tokens, include_pci=args.pci)
        if not args.json and not plain:
            print(short_banner(color=color))
            print()
        print(render_once(payload))
        return 0 if payload.get("ok") else 1

    if not watch:
        return once()

    # watch / graph / live loop
    history = LiveHistory(maxlen=60)
    title = " ".join(tokens) or "vitals"
    try:
        while True:
            payload = run_query(tokens, include_pci=args.pci)
            if args.json:
                print(json.dumps(payload), flush=True)
            else:
                print("\033[2J\033[H", end="")
                print(banner(color=color, subtitle=f"watch {title}  ·  every {args.interval}s  ·  Ctrl+C stop"))
                print()
                print(render_once(payload))
                if not args.no_graph:
                    history.push(extract_plot_series(payload))
                    print()
                    print(render_graph(history, title=f"live · {title}", color=color))
            if not payload.get("ok") and args.json:
                return 1
            time.sleep(max(args.interval, 0.25))
    except KeyboardInterrupt:
        if not args.json and not plain:
            print("\nstopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
