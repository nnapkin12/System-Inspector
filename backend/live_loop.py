"""
Live refresh loop.

Fetch never runs inside paint. Keystrokes only rewrite the prompt line
unless the board itself changed (new query, graph toggle, resize, help).
"""

from __future__ import annotations

import select
import signal
import sys
import termios
import time
import tty
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.live_mode import query_is_liveable
from backend.live_query import InventoryCache, poll_query_timed, run_query_timed
from backend.collectors.gpu import nvml_live_begin, nvml_live_end
from backend.resources import ALIASES, FIELD_ALIASES, parse_query
from backend.tui import (
    LiveHistory,
    enter_alt_screen,
    extract_metrics,
    extract_plot_series,
    leave_alt_screen,
    live_chrome,
    live_help_flash,
    logo_header,
    paint_frame,
    paint_from_row,
    render_graph,
    term_height,
)


@dataclass
class LiveState:
    tokens: list[str]
    interval: float
    show_graph: bool
    show_logo: bool = False
    draft: str = ""
    flash: str = ""
    flash_until: float = 0.0
    payload: dict | None = None
    last_good: dict | None = None
    refresh_slow: bool = False
    last_fetch: float = 0.0
    fetch_pending: bool = False
    fetch_slow: bool = False
    force_fetch: bool = True
    history: LiveHistory = field(default_factory=lambda: LiveHistory(maxlen=90))
    chrome_row: int = 1
    board_fp: tuple | None = None
    logo_block: str = ""
    logo_key: tuple[str, ...] = ()
    resized: bool = False
    need_full: bool = False
    painted: bool = False
    prev_flash: bool = False


def normalize_live_input(parts: list[str]) -> tuple[list[str] | None, str]:
    """
    Turn typed live words into query tokens.
    Returns (tokens, flash). tokens is None when input was a meta command or invalid.
    """
    if not parts:
        return ["status"], "watching overview (status)"

    low = [p.lower() for p in parts]

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
    if not query_is_liveable(kept):
        return None, f"{' '.join(kept)} is a snapshot — quit and run: si {' '.join(kept)}"
    flash = f"watching {' '.join(kept)}"
    if unknown:
        flash += f"  (skipped {', '.join(unknown)})"
    return kept, flash


def _visible_flash(state: LiveState) -> str:
    if time.time() >= state.flash_until:
        return ""
    flash = state.flash
    if not flash:
        return ""
    watch = " ".join(state.tokens) or "status"
    # Status bar already shows the active query — skip duplicate flash rows.
    if flash in (f"watching {watch}", "watching overview (status)"):
        return ""
    return flash


def _footer_line_count(state: LiveState) -> int:
    flash = _visible_flash(state)
    base = 3  # separator, status, prompt
    if not flash:
        return base
    return base + flash.count("\n") + 1


def _set_flash(state: LiveState, msg: str, seconds: float) -> None:
    state.flash = msg
    state.flash_until = time.time() + seconds


def _board_fingerprint(state: LiveState) -> tuple:
    fp: list[tuple] = []
    if state.show_logo:
        fp.append(("logo", state.logo_key))
    if state.show_graph:
        fp.append(("graph", len(state.history.series)))
    if state.refresh_slow:
        fp.append(("slow",))
    if state.payload is not None:
        for row in extract_metrics(state.payload):
            fp.append(
                (
                    row.get("label"),
                    row.get("pct"),
                    row.get("temp_c"),
                    row.get("rate"),
                    row.get("text"),
                )
            )
    return tuple(fp)


def _logo_block(state: LiveState, *, color: bool) -> str:
    if not state.show_logo:
        return ""
    key = tuple(state.tokens)
    if key != state.logo_key:
        watching = " ".join(state.tokens) or "status"
        state.logo_block = logo_header(watching=watching, color=color) + "\n"
        state.logo_key = key
    return state.logo_block


def _build_board(state: LiveState, render_once: Callable[..., str], color: bool) -> str:
    watching = " ".join(state.tokens) or "status"
    parts: list[str] = []
    logo = _logo_block(state, color=color)
    if logo:
        parts.append(logo.rstrip("\n"))
    if state.payload is not None:
        parts.append(render_once(state.payload, live=True))
    elif state.refresh_slow:
        parts.append("[Refresh Slow]")
    if state.show_graph:
        parts.append("")
        parts.append(render_graph(state.history, title=f"live · {watching}", color=color))
    return "\n".join(parts)


def _build_chrome(state: LiveState, color: bool) -> str:
    return live_chrome(
        watching=" ".join(state.tokens) or "status",
        interval=state.interval,
        draft=state.draft,
        flash=_visible_flash(state),
        graph=state.show_graph,
        refresh_slow=state.refresh_slow,
        color=color,
    )


def _layout_frame(
    state: LiveState,
    render_once: Callable[..., str],
    color: bool,
) -> tuple[str, str, int]:
    """Clip board above a fixed-height footer. Returns (board, chrome, chrome_row)."""
    chrome = _build_chrome(state, color)
    footer_rows = _footer_line_count(state)
    th = term_height()
    chrome_row = max(1, th - footer_rows + 1)
    max_board = max(1, chrome_row - 2)

    raw = _build_board(state, render_once, color)
    lines = raw.splitlines()[:max_board]
    return "\n".join(lines), chrome, chrome_row


def _paint_all(state: LiveState, render_once: Callable[..., str], color: bool) -> None:
    """One full-screen frame — avoids split board/chrome drift and stale rows."""
    board, chrome, chrome_row = _layout_frame(state, render_once, color)
    state.chrome_row = chrome_row
    frame = f"{board}\n\n{chrome}" if board else chrome
    paint_frame(frame)
    state.board_fp = _board_fingerprint(state)
    state.painted = True


def _paint_chrome(state: LiveState, color: bool) -> None:
    footer_rows = _footer_line_count(state)
    state.chrome_row = max(1, term_height() - footer_rows + 1)
    paint_from_row(state.chrome_row, _build_chrome(state, color))


def _apply_fetch_result(state: LiveState, payload: dict | None, timed_out: bool) -> str:
    """Update state from a completed (or timed-out) fetch. Returns paint mode."""
    state.fetch_pending = False
    state.last_fetch = time.monotonic()
    state.force_fetch = False
    if timed_out:
        state.refresh_slow = True
        state.fetch_slow = True
        state.payload = state.last_good
    else:
        state.refresh_slow = False
        state.fetch_slow = False
        state.payload = payload
        if state.payload and state.payload.get("ok"):
            state.last_good = state.payload
    if state.show_graph and state.payload is not None:
        state.history.push(extract_plot_series(state.payload))
    fp = _board_fingerprint(state)
    if fp == state.board_fp and state.painted:
        return "none"
    return "board"


def _poll_fetch(state: LiveState, *, include_pci: bool, verbose: bool, cache: InventoryCache) -> str:
    """Start or poll a background fetch. Never blocks the main thread."""
    now = time.monotonic()
    due = (
        state.force_fetch
        or state.payload is None
        or (now - state.last_fetch) >= state.interval
    )
    if not due and not state.fetch_pending:
        return "none"

    payload, timed_out, pending = poll_query_timed(
        state.tokens, include_pci=include_pci, verbose=verbose, cache=cache
    )
    if pending:
        state.fetch_pending = True
        if timed_out and not state.fetch_slow:
            state.refresh_slow = True
            state.fetch_slow = True
        return "none"

    return _apply_fetch_result(state, payload, timed_out)


def run_interactive_live(
    *,
    tokens: list[str],
    interval: float,
    show_graph: bool,
    show_logo: bool,
    color: bool,
    include_pci: bool,
    verbose: bool,
    render_once: Callable[..., str],
) -> int:
    """Live meters. Type the same words as `si …`, then Enter."""
    state = LiveState(
        tokens=list(tokens),
        interval=interval,
        show_graph=show_graph,
        show_logo=show_logo,
    )
    cache = InventoryCache()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    prev_winch = signal.getsignal(signal.SIGWINCH)

    def on_winch(_signum: int, _frame: Any) -> None:
        state.resized = True

    try:
        signal.signal(signal.SIGWINCH, on_winch)
        tty.setcbreak(fd)
        enter_alt_screen()
        nvml_live_begin()
        quit_live = False
        while not quit_live:
            flash_active = bool(_visible_flash(state))
            if state.painted and state.prev_flash and not flash_active:
                _paint_all(state, render_once, color)
            state.prev_flash = flash_active

            paint = _poll_fetch(
                state, include_pci=include_pci, verbose=verbose, cache=cache
            )
            if state.need_full or state.resized or not state.painted:
                state.resized = False
                state.need_full = False
                _paint_all(state, render_once, color)
            elif paint == "board":
                _paint_all(state, render_once, color)

            if quit_live:
                break

            remaining = max(0.05, state.interval - (time.monotonic() - state.last_fetch))
            if state.flash and time.time() < state.flash_until:
                remaining = min(remaining, max(0.05, state.flash_until - time.time()))
            if state.fetch_pending:
                remaining = min(remaining, 0.05)

            ready, _, _ = select.select(
                [sys.stdin], [], [], min(remaining, 0.2)
            )
            if state.resized:
                continue
            if not ready:
                continue

            action = _handle_key(state, sys.stdin.read(1))
            if action == "quit":
                quit_live = True
                break
            if action == "full":
                continue
            if action == "chrome":
                _paint_chrome(state, color)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGWINCH, prev_winch)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        nvml_live_end()
        leave_alt_screen()
        print("stopped.")
    return 0


def _handle_key(state: LiveState, ch: str) -> str:
    """
    Apply one key. Returns:
      quit    — leave live
      full    — break inner wait (fetch / full redraw)
      chrome  — rewrite prompt only
      ignore  — nothing
    """
    if not ch:
        return "ignore"

    if ch == "\x1b":
        if select.select([sys.stdin], [], [], 0.02)[0]:
            rest = sys.stdin.read(1)
            if rest == "[" and select.select([sys.stdin], [], [], 0.02)[0]:
                sys.stdin.read(1)
                return "ignore"
        state.draft = ""
        _set_flash(state, "cleared", 1.5)
        return "chrome"

    if ch == "\x03":
        return "quit"

    if ch in ("\r", "\n"):
        return _submit_draft(state)

    if ch in ("\x7f", "\b"):
        state.draft = state.draft[:-1]
        return "chrome"

    if not state.draft and ch == "?":
        _set_flash(state, live_help_flash(), 6.0)
        state.need_full = True
        return "full"

    if ch.isprintable() and len(state.draft) < 48:
        state.draft += ch
        return "chrome"

    return "ignore"


def _submit_draft(state: LiveState) -> str:
    parts = state.draft.strip().split()
    state.draft = ""
    new_tokens, msg = normalize_live_input(parts)
    if msg == "__quit__":
        return "quit"
    if msg == "__graph__":
        state.show_graph = not state.show_graph
        _set_flash(state, "charts on" if state.show_graph else "charts off", 2.0)
        state.force_fetch = True
        state.fetch_pending = False
        state.need_full = True
        return "full"
    if msg == "__faster__":
        state.interval = max(0.25, round(state.interval * 0.5, 2))
        _set_flash(state, f"faster · every {state.interval:g}s", 2.0)
        return "chrome"
    if msg == "__slower__":
        state.interval = min(10.0, round(state.interval * 2.0, 2))
        _set_flash(state, f"slower · every {state.interval:g}s", 2.0)
        return "chrome"
    if msg == "__help__":
        _set_flash(state, live_help_flash(), 6.0)
        state.need_full = True
        return "full"
    if new_tokens is None:
        _set_flash(state, msg, 3.0)
        if "\n" in msg:
            state.need_full = True
            return "full"
        return "chrome"
    state.tokens = new_tokens
    state.history = LiveHistory(maxlen=90)
    state.logo_key = ()
    state.board_fp = None
    state.fetch_pending = False
    state.fetch_slow = False
    state.force_fetch = True
    state.need_full = True
    return "full"


def run_piped_live(
    *,
    tokens: list[str],
    interval: float,
    show_graph: bool,
    show_logo: bool,
    color: bool,
    include_pci: bool,
    verbose: bool,
    json_mode: bool,
    plain: bool,
    render_once: Callable[..., str],
    maybe_redact: Callable[[dict], dict],
) -> int:
    """JSON / plain / non-TTY refresh loop (scripts and pipes)."""
    import json

    history = LiveHistory(maxlen=90)
    title = " ".join(tokens) or "status"
    logo_block = ""
    if show_logo and not json_mode:
        logo_block = logo_header(watching=title, color=color and not plain) + "\n\n"
    last_good: dict | None = None
    refresh_slow = False
    cache = InventoryCache()
    try:
        while True:
            payload, timed_out = run_query_timed(
                tokens, include_pci=include_pci, verbose=verbose, cache=cache
            )
            if timed_out:
                refresh_slow = True
                payload = last_good or {
                    "ok": False,
                    "resource": "live",
                    "error": "refresh timed out",
                }
            else:
                refresh_slow = False
                if payload and payload.get("ok"):
                    last_good = payload
            if json_mode:
                print(json.dumps(maybe_redact(payload or {})), flush=True)
            else:
                sys.stdout.write("\033[H")
                if plain:
                    body = render_once(payload or {}, live=False)
                    if refresh_slow:
                        body += "\n[Refresh Slow]"
                    print(logo_block + body, end="")
                else:
                    print(logo_block + render_once(payload or {}, live=True), end="")
                    if refresh_slow:
                        print("\n[Refresh Slow]", end="")
                    if show_graph and payload:
                        history.push(extract_plot_series(payload))
                        print()
                        print(render_graph(history, title=f"live · {title}", color=color), end="")
                sys.stdout.write("\n\033[J")
                sys.stdout.flush()
            if not payload.get("ok") and json_mode and not timed_out:
                return 1
            time.sleep(max(interval, 0.25))
    except KeyboardInterrupt:
        if not json_mode and not plain:
            print("\nstopped.")
        return 0
