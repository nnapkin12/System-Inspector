"""
Terminal chrome for System Inspector CLI: banner, meters, live ASCII graphs.
"""

from __future__ import annotations

import collections
import re
import shutil
import sys
from typing import Any

# Soft red / gray ANSI (disabled if not a TTY or --plain)
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_WHITE = "\033[97m"


def use_color(enabled: bool = True) -> bool:
    return enabled and sys.stdout.isatty()


def c(text: str, *codes: str, color: bool) -> str:
    if not color or not codes:
        return text
    return "".join(codes) + text + _RESET


BANNER_LINES = [
    r"  ____            ___                          __",
    r" / __/_ _____    / _/__ ____ ___  ___ ______  / /____  ____",
    r"_\ \/ // (_-<   / _/ _ `/ _ \/ -_|_-</ __/ _ \/ __/ _ \/ __/",
    r"/___/\_, /___/  /_/ \_,_/_//_/\__/___/\__/\___/\__/\___/_/",
    r"    /___/                                                  ",
]


def banner(color: bool = True, subtitle: str | None = None) -> str:
    """Compact brand header for CLI / watch."""
    lines = [c(line, _RED, _BOLD, color=color) for line in BANNER_LINES]
    tag = subtitle or "local hardware · terminal first · Ctrl+C to stop watches"
    lines.append(c("  " + tag, _DIM, color=color))
    lines.append(c("  " + "─" * min(56, max(40, term_width() - 4)), _DIM, color=color))
    return "\n".join(lines)


def short_banner(color: bool = True) -> str:
    title = c(" SYSTEM INSPECTOR ", _BOLD, _RED, color=color)
    rule = c("─" * 18, _DIM, color=color)
    return f"{rule}{title}{rule}"


def term_width() -> int:
    try:
        return max(40, shutil.get_terminal_size((80, 24)).columns)
    except OSError:
        return 80


def meter(value: float | None, width: int = 18, color: bool = True) -> str:
    """Unicode block bar for 0–100 percentages (or any 0–100 scale)."""
    if value is None:
        empty = "─" * width
        return c(f"[{empty}]", _DIM, color=color)
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return c(f"[{'─' * width}]", _DIM, color=color)
    filled = int(round((v / 100.0) * width))
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    style = _RED if v >= 85 else _WHITE
    return c(f"[{bar}]", style, color=color) + c(f" {int(round(v))}%", _DIM, color=color)


def temp_meter(celsius: float | None, width: int = 18, color: bool = True, lo: float = 30, hi: float = 95) -> str:
    """Map temperature into a bar (not %) for visual scale."""
    if celsius is None:
        return meter(None, width=width, color=color)
    try:
        t = float(celsius)
    except (TypeError, ValueError):
        return meter(None, width=width, color=color)
    # normalize lo..hi → 0..100
    pct = (t - lo) / (hi - lo) * 100.0
    if t is None:
        return meter(None, width=width, color=color)
    filled_m = meter(pct, width=width, color=color)
    # replace trailing percent with °C
    filled_m = re.sub(r"\s+\d+%$", "", filled_m)
    return filled_m + c(f" {int(round(t))}°C", _DIM, color=color)


def decorate_human(text: str, color: bool = True) -> str:
    """
    Post-process plain human output: add meters next to known Load / RAM style lines.
    Light pass — doesn't reparse JSON.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        # CPU Load   10%
        m = re.match(r"^(\s*Load\s+)(\d+)%(\s*)$", line)
        if m:
            out_lines.append(f"{m.group(1)}{meter(float(m.group(2)), color=color)}")
            continue
        m = re.match(r"^(\s*Memory\s+)(\d+)%(.*)$", line)
        if m:
            out_lines.append(f"{m.group(1)}{meter(float(m.group(2)), color=color)}{m.group(3)}")
            continue
        # Live  CPU 10%  ·  GPU 0%  ·  RAM 60%
        if line.startswith("Live  ") and "%" in line:
            parts = line.replace("Live  ", "", 1)
            chunks = [p.strip() for p in parts.split("·")]
            rebuilt = []
            for ch in chunks:
                mm = re.match(r"^(CPU|GPU|RAM)\s+(\d+)%$", ch.strip())
                if mm:
                    rebuilt.append(f"{mm.group(1)} {meter(float(mm.group(2)), width=12, color=color)}")
                else:
                    rebuilt.append(ch)
            out_lines.append("Live  " + "  ·  ".join(rebuilt))
            continue
        # indented "Load 0%" under GPU
        m = re.match(r"^(\s+Load\s+)(\d+)%(.*)$", line)
        if m:
            out_lines.append(f"{m.group(1)}{meter(float(m.group(2)), width=14, color=color)}{m.group(3)}")
            continue
        # Temp   40°C  → add heat bar
        m = re.match(r"^(\s*Temp\s+)(\d+)°C\s*$", line)
        if m:
            out_lines.append(f"{m.group(1)}{temp_meter(float(m.group(2)), width=14, color=color)}")
            continue
        m = re.match(r"^(CPU temp\s+)(\d+)°C\s*$", line)
        if m:
            out_lines.append(f"{m.group(1)}{temp_meter(float(m.group(2)), color=color)}")
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------- live graph (plotext) ----------


def extract_plot_series(payload: dict) -> list[tuple[str, float | None]]:
    """Pull numbered series points from a resource payload for live graphing."""
    if not payload.get("ok"):
        return []
    r = payload.get("resource")
    d = payload.get("data") or {}
    fields = set(payload.get("fields") or [])

    series: list[tuple[str, float | None]] = []

    if r == "bundle":
        for part in payload.get("results") or []:
            series.extend(extract_plot_series(part))
        return series

    if r == "cpu":
        if "temp" in fields or (fields and "usage" not in fields and "name" not in fields and "temp" in fields):
            series.append(("CPU °C", d.get("temp_c")))
        elif "usage" in fields:
            series.append(("CPU %", d.get("usage_percent")))
        else:
            series.append(("CPU %", d.get("usage_percent")))
            series.append(("CPU °C", d.get("temp_c")))
        return series

    if r == "gpu":
        devices = d.get("devices") or []
        for i, g in enumerate(devices):
            name = (g.get("name") or f"GPU{i}")[:22]
            if "temp" in fields and "usage" not in fields:
                series.append((f"{name} °C", g.get("temp_c")))
            elif "usage" in fields and "temp" not in fields:
                series.append((f"{name} %", g.get("usage_percent")))
            else:
                series.append((f"{name} %", g.get("usage_percent")))
                series.append((f"{name} °C", g.get("temp_c")))
        return series

    if r == "temps":
        series.append(("CPU °C", d.get("cpu_c")))
        for g in d.get("gpus") or []:
            n = (g.get("name") or "GPU")[:22]
            series.append((f"{n} °C", g.get("temp_c")))
        return series

    if r == "memory":
        ram = d.get("ram") or d
        series.append(("RAM %", ram.get("percent")))
        return series

    if r == "status":
        live = d.get("live") or {}
        series.append(("CPU %", live.get("cpu_percent")))
        series.append(("GPU %", live.get("gpu_percent")))
        series.append(("RAM %", live.get("ram_percent")))
        series.append(("CPU °C", live.get("cpu_temp_c")))
        series.append(("GPU °C", live.get("gpu_temp_c")))
        return series

    if r == "disk":
        rates = d.get("rates_mbs") or {}
        series.append(("Read MB/s", rates.get("read")))
        series.append(("Write MB/s", rates.get("write")))
        return series

    if r == "net":
        rates = d.get("rates_mbs") or {}
        series.append(("↓ MB/s", rates.get("recv")))
        series.append(("↑ MB/s", rates.get("sent")))
        return series

    return series


class LiveHistory:
    def __init__(self, maxlen: int = 60) -> None:
        self.maxlen = maxlen
        self.series: dict[str, collections.deque[float]] = {}

    def push(self, points: list[tuple[str, float | None]]) -> None:
        seen = set()
        for name, val in points:
            seen.add(name)
            if name not in self.series:
                self.series[name] = collections.deque(maxlen=self.maxlen)
            if val is None:
                continue
            try:
                self.series[name].append(float(val))
            except (TypeError, ValueError):
                continue
        # drop series no longer present
        for k in list(self.series.keys()):
            if k not in seen:
                del self.series[k]

    def nonempty(self) -> bool:
        return any(len(v) > 0 for v in self.series.values())


def render_graph(history: LiveHistory, title: str, color: bool = True) -> str:
    """
    Live multi-series line chart. Uses plotext when available;
    otherwise a simple block sparkline fallback.
    """
    if not history.nonempty():
        return c("  (graph: collecting samples…)", _DIM, color=color)

    try:
        import plotext as plt  # type: ignore
    except ImportError:
        return _spark_fallback(history, title, color=color)

    plt.clear_figure()
    # Don't clear whole terminal here — caller manages the frame
    width = max(50, min(term_width() - 2, 100))
    height = 18
    plt.plotsize(width, height)
    plt.title(title)
    plt.theme("clear" if not color else "dark")

    # Prefer red-ish colours for brand
    colors = ["red+", "orange+", "tomato+", "salmon+", "white+", "gray+"]
    i = 0
    for name, data in history.series.items():
        if len(data) < 1:
            continue
        plt.plot(list(data), label=name, marker="braille", color=colors[i % len(colors)])
        i += 1

    plt.xlabel("samples")
    # capture plotext stdout
    try:
        return plt.build()
    except Exception:
        # older plotext API
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            plt.show()
        return buf.getvalue()


def _spark_fallback(history: LiveHistory, title: str, color: bool = True) -> str:
    blocks = " ▁▂▃▄▅▆▇█"
    lines = [c(f"  {title} (install plotext for full graphs: pip install plotext)", _DIM, color=color)]
    for name, data in history.series.items():
        if not data:
            continue
        vals = list(data)
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        spark = "".join(blocks[min(8, int((v - lo) / span * 8))] for v in vals[-40:])
        last = vals[-1]
        lines.append(f"  {name:16} {spark}  {last:.1f}")
    return "\n".join(lines)
