"""
Braille line plots for `si graph` / `--graph`.

Regular `si status` / `si cpu` never paint this. Samples stay raw
(no load EMA) so the line is the real vital.
"""

from __future__ import annotations

from collections import deque
from math import ceil
from typing import Literal

from backend.tui import (
    _BOLD,
    _DIM,
    _sev_style,
    _sev_style_battery,
    _visible_len,
    _fit_line,
    c,
    extract_plot_series,
    term_height,
    term_width,
)

# Braille dots in one cell (2×4):
# 1 4
# 2 5
# 3 6
# 7 8
_DOT = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)

SeriesPoint = tuple[str, float | None, Literal["pct", "temp", "rate"]]

# Fixed scales so a quiet 2% does not look like 50%.
_SCALE = {
    "pct": (0.0, 100.0, "%"),
    "temp": (15.0, 100.0, "°C"),
    "rate": (0.0, 10.0, " MB/s"),
}


class LiveHistory:
    def __init__(self, maxlen: int = 180) -> None:
        self.maxlen = maxlen
        self.series: dict[str, tuple[str, deque[float]]] = {}

    def push(self, points: list[SeriesPoint]) -> None:
        seen: set[str] = set()
        for name, val, unit in points:
            seen.add(name)
            if name not in self.series:
                self.series[name] = (unit, deque(maxlen=self.maxlen))
            if val is None:
                continue
            try:
                self.series[name][1].append(float(val))
            except (TypeError, ValueError):
                continue
        for key in list(self.series.keys()):
            if key not in seen:
                del self.series[key]

    def nonempty(self) -> bool:
        return any(len(dq) > 0 for _, dq in self.series.values())

    def fingerprint(self) -> tuple:
        return tuple(
            (name, len(dq), dq[0] if dq else None, dq[-1] if dq else None)
            for name, (_unit, dq) in self.series.items()
        )


class BrailleCanvas:
    """Pixel grid packed into Unicode Braille (2×4 dots per character)."""

    def __init__(self, cols: int, rows: int) -> None:
        self.cols = max(8, cols)
        self.rows = max(3, rows)
        self.px_w = self.cols * 2
        self.px_h = self.rows * 4
        self.cells = [0] * (self.cols * self.rows)

    def plot(self, x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= self.px_w or y >= self.px_h:
            return
        col = x // 2
        from_top = self.px_h - 1 - y
        row = from_top // 4
        dy = from_top % 4
        dx = x % 2
        self.cells[row * self.cols + col] |= _DOT[dy][dx]

    def line(self, x0: int, y0: int, x1: int, y1: int) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            self.plot(x, y)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def rows_text(self) -> list[str]:
        out: list[str] = []
        for r in range(self.rows):
            chars: list[str] = []
            for col in range(self.cols):
                bits = self.cells[r * self.cols + col]
                chars.append(chr(0x2800 + bits) if bits else " ")
            out.append("".join(chars))
        return out


def _scale(unit: str, vals: list[float]) -> tuple[float, float, str]:
    lo, hi, suffix = _SCALE.get(unit, _SCALE["pct"])
    if unit == "rate":
        hi = max(hi, max(vals, default=0.0) * 1.15, 1.0)
    return lo, hi, suffix


def map_y(v: float, lo: float, hi: float, px_h: int) -> int:
    if hi <= lo or px_h <= 1:
        return 0
    t = (v - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    return int(round(t * (px_h - 1)))


def _plot_series(vals: list[float], lo: float, hi: float, cols: int, rows: int) -> list[str]:
    canvas = BrailleCanvas(cols, rows)
    if not vals:
        return canvas.rows_text()
    n = len(vals)
    xs: list[int] = []
    ys: list[int] = []
    for i, v in enumerate(vals):
        x = 0 if n == 1 else int(round(i * (canvas.px_w - 1) / (n - 1)))
        y = map_y(v, lo, hi, canvas.px_h)
        xs.append(x)
        ys.append(y)
    for i in range(1, len(xs)):
        canvas.line(xs[i - 1], ys[i - 1], xs[i], ys[i])
    canvas.plot(xs[0], ys[0])
    canvas.plot(xs[-1], ys[-1])
    return canvas.rows_text()


def _y_labels(lo: float, hi: float, rows: int) -> list[str]:
    labels = [""] * rows
    if rows < 2:
        return [f"{lab:>4}" for lab in labels]

    def fmt(v: float) -> str:
        if abs(v - round(v)) < 0.05:
            return f"{int(round(v))}"
        if abs(v) >= 10:
            return f"{v:.0f}"
        return f"{v:.1f}"

    labels[0] = fmt(hi)
    labels[-1] = fmt(lo)
    if rows >= 4:
        labels[rows // 2] = fmt((hi + lo) / 2)
    return [f"{lab:>4}" for lab in labels]


def _pad(s: str, width: int) -> str:
    vis = _visible_len(s)
    if vis >= width:
        return _fit_line(s, width)
    return s + (" " * (width - vis))


def _plot_style(last: float, unit: str, *, battery: bool = False) -> tuple[str, ...]:
    if battery:
        return _sev_style_battery(last, plugged=False)
    if unit == "temp":
        return _sev_style(last, hot=True)
    if unit == "rate":
        return (_DIM,)
    return _sev_style(last, hot=False)


def render_one_plot(
    name: str,
    vals: list[float],
    unit: str,
    *,
    cols: int,
    rows: int,
    color: bool,
    width: int | None = None,
) -> list[str]:
    lo, hi, suffix = _scale(unit, vals)
    last = vals[-1] if vals else 0.0
    style = _plot_style(last, unit, battery=name.upper().startswith("BAT"))
    if unit == "rate":
        value = f"{last:.2f}{suffix}".rstrip()
    elif unit == "temp":
        value = f"{last:.0f}{suffix}"
    else:
        value = f"{last:.0f}{suffix}"
    title = c(f"  {name}", _BOLD, color=color) + c(f"  {value}", _BOLD, *style, color=color)
    body = _plot_series(vals, lo, hi, cols, rows)
    ylabs = _y_labels(lo, hi, rows)
    lines = [title]
    for lab, row in zip(ylabs, body):
        axis = "┤" if lab.strip() else "│"
        painted = c(row, *style, color=color)
        lines.append(c(f"  {lab}{axis}", _DIM, color=color) + painted)
    lines.append(c("      └" + "─" * cols, _DIM, color=color))
    if width is not None:
        return [_pad(ln, width) for ln in lines]
    return lines


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def series_from_payload(payload: dict) -> list[SeriesPoint]:
    """Numeric series for plots. Status also gets VRAM / swap / battery / net."""
    points = list(extract_plot_series(payload))
    if not payload.get("ok"):
        return points
    r = payload.get("resource")
    d = payload.get("data") or {}
    names = {p[0] for p in points}

    def add(name: str, val: float | None, unit: Literal["pct", "temp", "rate"]) -> None:
        if val is None or name in names:
            return
        names.add(name)
        points.append((name, val, unit))

    if r == "status":
        live = d.get("live") or {}
        vu, vt = _f(live.get("gpu_vram_used_mb")), _f(live.get("gpu_vram_total_mb"))
        if vu is not None and vt and vt > 0:
            add("VRAM %", vu / vt * 100.0, "pct")
        swap = _f(live.get("swap_percent"))
        if swap is not None and swap > 0.5:
            add("SWAP %", swap, "pct")
        bat = _f(live.get("battery_percent"))
        if bat is not None:
            add("BAT %", bat, "pct")
        add("Net ↓", _f(live.get("net_recv_mbs")), "rate")
        add("Net ↑", _f(live.get("net_sent_mbs")), "rate")
    elif r == "gpu":
        for i, g in enumerate(d.get("devices") or []):
            vu, vt = _f(g.get("vram_used_mb")), _f(g.get("vram_total_mb"))
            if vu is None or not vt or vt <= 0:
                continue
            name = (g.get("name") or f"GPU{i}")[:28]
            add(f"{name} VRAM", vu / vt * 100.0, "pct")
    elif r == "memory":
        swap = (d.get("swap") or {}) if isinstance(d, dict) else {}
        pct = _f(swap.get("percent"))
        if pct is not None and pct > 0.5:
            add("SWAP %", pct, "pct")
    return points


def _grid_shape(n: int, width: int) -> tuple[int, int]:
    if n <= 1 or width < 88:
        return 1, n
    cols = 2
    return cols, ceil(n / cols)


def render_graph_board(
    history: LiveHistory,
    *,
    interval: float,
    color: bool = True,
    watching: str = "",
    width: int | None = None,
    height: int | None = None,
) -> str:
    tw = width if width is not None else term_width()
    th = height if height is not None else max(12, term_height() - 14)
    if not history.nonempty():
        return c("  collecting samples…", _DIM, color=color)

    items: list[tuple[str, str, list[float]]] = []
    for name, (unit, dq) in history.series.items():
        vals = list(dq)
        if vals:
            items.append((name, unit, vals))
    if not items:
        return c("  no numeric series yet", _DIM, color=color)

    n = len(items)
    grid_cols, grid_rows = _grid_shape(n, tw)
    # title + axis + optional gap between plot-rows
    overhead = grid_rows * 3
    body = max(3, min(10, (th - overhead - 1) // max(1, grid_rows)))
    if grid_cols == 2:
        plot_width = max(36, (tw - 2) // 2)
        cols = max(20, plot_width - 8)
    else:
        plot_width = tw
        cols = max(24, tw - 10)

    rendered = [
        render_one_plot(
            name,
            vals,
            unit,
            cols=cols,
            rows=body,
            color=color,
            width=plot_width if grid_cols == 2 else None,
        )
        for name, unit, vals in items
    ]

    out: list[str] = []
    if watching:
        out.append(c(f"  graph  {watching}", _DIM, color=color))
        out.append("")
    for r in range(grid_rows):
        if r:
            out.append("")
        pair = rendered[r * grid_cols : r * grid_cols + grid_cols]
        if len(pair) == 1:
            out.extend(pair[0])
            continue
        h = max(len(p) for p in pair)
        padded = [p + [""] * (h - len(p)) for p in pair]
        for lines in zip(*padded):
            out.append("".join(lines))

    span = max(1, len(items[0][2]) - 1) * interval
    left = f"{span:.0f}s ago"
    out.append(c(f"      {left}" + " " * max(1, cols - len(left) - 3) + "now", _DIM, color=color))
    return "\n".join(_fit_line(ln, tw) for ln in out)
