"""
System Inspector CLI — short commands like: gpu · cpu temp · motherboard

Primary name: sysinspect
Also works as:        si   (wrapper script)

Does not require a server. Calls collectors directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.format import format_human  # noqa: E402
from backend.help_text import FULL_HELP  # noqa: E402
from backend.live_loop import run_interactive_live, run_piped_live  # noqa: E402
from backend.live_mode import should_enter_live  # noqa: E402
from backend.query import parse_query  # noqa: E402
from backend.redact import redact_payload  # noqa: E402
from backend.resources import run_query  # noqa: E402
from backend.tui import (  # noqa: E402
    banner,
    decorate_human,
    format_watch_dashboard,
    logo_header,
    use_color,
)


def _print_help(*, color: bool, plain: bool) -> None:
    if not plain:
        print(banner(color=color))
        print()
    print(FULL_HELP)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    force_live = False
    force_graph = False
    if argv and argv[0].lower() in ("watch", "graph", "live"):
        if argv[0].lower() == "graph":
            force_graph = True
        force_live = True
        argv = argv[1:]

    parser = argparse.ArgumentParser(
        prog="sysinspect",
        description="System Inspector CLI — short hardware & vitals queries",
        add_help=False,
    )
    parser.add_argument("tokens", nargs="*", help="resource and optional field words")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print one snapshot (default for sensors is live on a TTY)",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        help="Mask serials, UUIDs, boot_id in output (useful for logs/sharing)",
    )
    parser.add_argument("--pci", action="store_true", help="Include PCI list for scan")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Watch interval seconds (default 1)",
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Watch: also draw sparklines (default is large bar meters only)",
    )
    parser.add_argument(
        "--no-logo",
        action="store_true",
        help="Hide the SI ASCII logo header (shown by default on human output)",
    )
    parser.add_argument("--plain", "-p", action="store_true", help="No color or meters")
    parser.add_argument("--verbose", "-v", action="store_true", help="Extra JSON fields")
    parser.add_argument("--all", action="store_true", help="Same as --verbose")
    parser.add_argument("--help", "-h", action="store_true")

    args, unknown = parser.parse_known_args(argv)
    plain = args.plain
    verbose = args.verbose or args.all
    color = use_color(not plain)

    tokens = list(args.tokens) + list(unknown)
    tokens = [t for t in tokens if not t.startswith("-")]
    if force_live and not tokens:
        tokens = ["status"]
    if args.help or not tokens or [t.lower() for t in tokens] == ["help"]:
        _print_help(color=color, plain=plain)
        return 0

    show_graph = bool(force_graph or args.graph) and not plain
    resources, _fields, _unknown = parse_query(tokens)
    # Logo on by default for human output; skip when plain, opted out, or version card.
    show_logo = (
        not plain
        and not args.no_logo
        and not args.json
        and not (resources == ["version"] and not _fields)
    )

    def emit_logo(watching: str = "") -> None:
        if not show_logo:
            return
        hdr = logo_header(watching=watching or " ".join(tokens), color=color)
        print(hdr)
        print()

    def maybe_redact(payload: dict) -> dict:
        if args.redact:
            return redact_payload(payload)
        return payload

    def render_once(payload: dict, *, live: bool = False) -> str:
        payload = maybe_redact(payload)
        if args.json:
            return json.dumps(payload, indent=2)
        if live and not plain:
            return format_watch_dashboard(payload, color=color)
        body = format_human(payload, color=color, verbose=verbose)
        if not plain:
            body = decorate_human(body, color=color)
        return body

    live = should_enter_live(
        tokens,
        force_live=force_live,
        once=args.once,
        json_mode=args.json,
        plain=plain,
        stdin_tty=sys.stdin.isatty(),
        stdout_tty=sys.stdout.isatty(),
    )
    if not live:
        payload = run_query(tokens, include_pci=args.pci, verbose=verbose)
        emit_logo()
        print(render_once(payload, live=False))
        return 0 if payload.get("ok") else 1

    interval = max(args.interval, 0.25)
    interactive = (
        not args.json
        and not plain
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )
    if interactive:
        return run_interactive_live(
            tokens=tokens,
            interval=interval,
            show_graph=show_graph,
            show_logo=show_logo,
            color=color,
            include_pci=args.pci,
            verbose=verbose,
            render_once=render_once,
        )
    return run_piped_live(
        tokens=tokens,
        interval=interval,
        show_graph=show_graph,
        show_logo=show_logo,
        color=color,
        include_pci=args.pci,
        verbose=verbose,
        json_mode=args.json,
        plain=plain,
        render_once=render_once,
        maybe_redact=maybe_redact,
    )


if __name__ == "__main__":
    raise SystemExit(main())
