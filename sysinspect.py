"""
System Inspector CLI — short commands like: gpu · cpu temp · motherboard

Primary name: sysinspect
Also works as:        si   (wrapper script)

Does not require a server. Calls collectors directly.
"""

from __future__ import annotations

import argparse
import json
import select
import sys
import termios
import time
import tty
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.redact import redact_payload  # noqa: E402
from backend.live_query import run_query_timed  # noqa: E402
from backend.format import format_human  # noqa: E402
from backend.resources import (  # noqa: E402
    ALIASES,
    FIELD_ALIASES,
    list_commands_help,
    parse_query,
    run_query,
)
from backend.tui import (  # noqa: E402
    LiveHistory,
    banner,
    clear_home,
    decorate_human,
    enter_alt_screen,
    extract_plot_series,
    format_watch_dashboard,
    leave_alt_screen,
    live_chrome,
    live_help_flash,
    render_graph,
    use_color,
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    plain = "--plain" in argv or "-p" in argv
    verbose = "--verbose" in argv or "-v" in argv or "--all" in argv
    argv = [a for a in argv if a not in ("--plain", "-p", "--verbose", "-v", "--all")]
    color = use_color(not plain)

    if not argv or argv[0] in ("-h", "--help", "help"):
        if not plain:
            print(banner(color=color))
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
        help="Watch: also draw line charts (default is large bar meters only)",
    )
    parser.add_argument("--help", "-h", action="store_true")

    watch = False
    force_graph = False
    if argv and argv[0].lower() in ("watch", "graph", "live"):
        if argv[0].lower() == "graph":
            force_graph = True
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

    if watch and not tokens:
        tokens = ["status"]

    if not tokens:
        if not plain:
            print(banner(color=color))
            print()
        print(list_commands_help())
        return 0

    show_graph = bool(force_graph or args.graph) and not plain

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

    def once() -> int:
        payload = run_query(tokens, include_pci=args.pci, verbose=verbose)
        print(render_once(payload, live=False))
        return 0 if payload.get("ok") else 1

    if not watch:
        return once()

    # JSON / plain live: simple refresh loop (scripts / pipes)
    interactive = (
        not args.json
        and not plain
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )
    if interactive:
        return _run_interactive_live(
            tokens=tokens,
            interval=max(args.interval, 0.25),
            show_graph=show_graph,
            color=color,
            include_pci=args.pci,
            verbose=verbose,
            render_once=render_once,
        )

    history = LiveHistory(maxlen=90)
    title = " ".join(tokens) or "status"
    last_good: dict | None = None
    refresh_slow = False
    try:
        while True:
            payload, timed_out = run_query_timed(tokens, include_pci=args.pci, verbose=verbose)
            if timed_out:
                refresh_slow = True
                payload = last_good or {"ok": False, "resource": "live", "error": "refresh timed out"}
            else:
                refresh_slow = False
                if payload and payload.get("ok"):
                    last_good = payload
            if args.json:
                print(json.dumps(maybe_redact(payload or {})), flush=True)
            else:
                print("\033[2J\033[H", end="")
                if plain:
                    body = render_once(payload or {}, live=False)
                    if refresh_slow:
                        body += "\n[Refresh Slow]"
                    print(body)
                else:
                    print(render_once(payload or {}, live=True))
                    if refresh_slow:
                        print("\n[Refresh Slow]")
                    if show_graph and payload:
                        history.push(extract_plot_series(payload))
                        print()
                        print(render_graph(history, title=f"live · {title}", color=color))
            if not payload.get("ok") and args.json and not timed_out:
                return 1
            time.sleep(max(args.interval, 0.25))
    except KeyboardInterrupt:
        if not args.json and not plain:
            print("\nstopped.")
        return 0


def _normalize_live_tokens(parts: list[str]) -> tuple[list[str] | None, str]:
    """
    Turn typed live words into query tokens.
    Returns (tokens, flash). tokens is None when input was invalid.
    """
    if not parts:
        return ["status"], "watching overview (status)"

    low = [p.lower() for p in parts]

    # Whole-line meta commands (words, not mystery hotkeys)
    if len(low) == 1 and low[0] in ("quit", "exit", "q"):
        return None, "__quit__"
    if len(low) == 1 and low[0] in ("graph", "charts"):
        return None, "__graph__"
    if len(low) == 1 and low[0] in ("faster", "fast"):
        return None, "__faster__"
    if len(low) == 1 and low[0] in ("slower", "slow"):
        return None, "__slower__"
    if len(low) == 1 and low[0] in ("help", "?"):
        return None, "__help__"
    if len(low) == 1 and low[0] in ("clear", "overview", "status", "reset"):
        return ["status"], "watching overview (status)"

    resources, fields, unknown = parse_query(low)
    if unknown and not resources and not fields:
        return None, f"don't know “{' '.join(unknown)}” — try: cpu gpu ram temps disk net"
    kept = [t for t in low if t in ALIASES or t in FIELD_ALIASES]
    if not kept:
        return None, "type a hardware word: cpu gpu ram temps disk net…"
    flash = f"watching {' '.join(kept)}"
    if unknown:
        flash += f"  (skipped {', '.join(unknown)})"
    return kept, flash


def _run_interactive_live(
    *,
    tokens: list[str],
    interval: float,
    show_graph: bool,
    color: bool,
    include_pci: bool,
    verbose: bool,
    render_once,
) -> int:
    """
    Live meters with a prompt: type the same words as `si …`, then Enter.
    When the prompt is empty, a few single keys work (q / g / + / − / ?).
    """
    history = LiveHistory(maxlen=90)
    draft = ""
    flash = ""
    flash_until = 0.0
    payload: dict | None = None
    last_good: dict | None = None
    refresh_slow = False
    last_fetch = 0.0
    force_fetch = True
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    def paint() -> None:
        nonlocal payload, last_fetch, force_fetch, last_good, refresh_slow
        watching = " ".join(tokens) or "status"
        now = time.monotonic()
        if force_fetch or payload is None or (now - last_fetch) >= interval:
            fetched, timed_out = run_query_timed(
                tokens, include_pci=include_pci, verbose=verbose
            )
            last_fetch = now
            force_fetch = False
            if timed_out:
                refresh_slow = True
                payload = last_good
            else:
                refresh_slow = False
                payload = fetched
                if payload and payload.get("ok"):
                    last_good = payload
            if show_graph and payload is not None:
                history.push(extract_plot_series(payload))
        clear_home()
        if payload is not None:
            print(render_once(payload, live=True))
        elif refresh_slow:
            print("[Refresh Slow]")
        if show_graph:
            print()
            print(render_graph(history, title=f"live · {watching}", color=color))
        print()
        show_flash = flash if time.time() < flash_until else ""
        print(
            live_chrome(
                watching=watching,
                interval=interval,
                draft=draft,
                flash=show_flash,
                graph=show_graph,
                refresh_slow=refresh_slow,
                color=color,
            ),
            flush=True,
        )

    try:
        tty.setcbreak(fd)
        enter_alt_screen()
        quit_live = False
        while not quit_live:
            paint()
            # Wait until next sensor refresh, but wake immediately on keypress
            deadline = last_fetch + interval
            while not quit_live:
                remaining = max(0.0, deadline - time.monotonic())
                # Also wake when a flash message expires so chrome clears
                if flash and time.time() < flash_until:
                    remaining = min(remaining, max(0.05, flash_until - time.time()))
                ready, _, _ = select.select([sys.stdin], [], [], min(remaining, 0.2) if remaining else 0)
                if not ready:
                    # time for refresh or flash clear
                    if time.monotonic() >= deadline or (flash and time.time() >= flash_until):
                        break
                    continue

                ch = sys.stdin.read(1)
                if not ch:
                    continue

                redraw = True
                # Escape sequences: Esc alone clears draft; arrows ignored
                if ch == "\x1b":
                    if select.select([sys.stdin], [], [], 0.02)[0]:
                        rest = sys.stdin.read(1)
                        if rest == "[" and select.select([sys.stdin], [], [], 0.02)[0]:
                            sys.stdin.read(1)
                            redraw = False
                        else:
                            draft = ""
                            flash = "cleared"
                            flash_until = time.time() + 1.5
                    else:
                        draft = ""
                        flash = "cleared"
                        flash_until = time.time() + 1.5
                    if redraw:
                        paint()
                    continue

                if ch == "\x03":  # Ctrl+C
                    quit_live = True
                    break

                if ch in ("\r", "\n"):
                    parts = draft.strip().split()
                    draft = ""
                    new_tokens, msg = _normalize_live_tokens(parts)
                    if msg == "__quit__":
                        quit_live = True
                        break
                    if msg == "__graph__":
                        show_graph = not show_graph
                        flash = "charts on" if show_graph else "charts off"
                        flash_until = time.time() + 2.0
                        force_fetch = True
                        break
                    if msg == "__faster__":
                        interval = max(0.25, round(interval * 0.5, 2))
                        flash = f"faster · every {interval:g}s"
                        flash_until = time.time() + 2.0
                        break
                    if msg == "__slower__":
                        interval = min(10.0, round(interval * 2.0, 2))
                        flash = f"slower · every {interval:g}s"
                        flash_until = time.time() + 2.0
                        break
                    if msg == "__help__":
                        flash = live_help_flash()
                        flash_until = time.time() + 6.0
                        paint()
                        continue
                    if new_tokens is None:
                        flash = msg
                        flash_until = time.time() + 3.0
                        paint()
                        continue
                    tokens = new_tokens
                    history = LiveHistory(maxlen=90)
                    flash = msg
                    flash_until = time.time() + 2.5
                    force_fetch = True
                    break

                if ch in ("\x7f", "\b"):
                    draft = draft[:-1]
                    paint()
                    continue

                # Only ? is a single-key action — letter shortcuts steal words like "gpu"
                if not draft and ch == "?":
                    flash = live_help_flash()
                    flash_until = time.time() + 6.0
                    paint()
                    continue

                if ch.isprintable() and len(draft) < 48:
                    draft += ch
                    paint()
                    continue
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        leave_alt_screen()
        print("stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
