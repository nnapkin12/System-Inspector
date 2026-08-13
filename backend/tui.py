"""
Terminal chrome for System Inspector CLI: banner, meters, live charts.
"""

from __future__ import annotations

import collections
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Literal

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Soft red / gray ANSI (disabled if not a TTY or --plain)
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_YEL = "\033[93m"
_GRN = "\033[92m"
_WHITE = "\033[97m"


def use_color(enabled: bool = True) -> bool:
    return enabled and sys.stdout.isatty()


def c(text: str, *codes: str, color: bool) -> str:
    if not color or not codes:
        return text
    return "".join(codes) + text + _RESET


def health_style(level: str) -> tuple[str, ...]:
    if level == "good":
        return (_GRN,)
    if level == "warn":
        return (_YEL,)
    if level == "bad":
        return (_RED,)
    return (_DIM,)


def paint_health(text: str, level: str, *, color: bool) -> str:
    return c(text, *health_style(level), color=color)


# Fallback if logo file missing
_SI_MARK_FALLBACK = [
    "  ████████   ██████",
    "  ██           ██",
    "  ████████     ██",
    "        ██     ██",
    "  ████████   ██████",
]


def _visible_len(s: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def load_si_logo() -> list[str]:
    path = _PROJECT_ROOT / "ascii art" / "systeminspect logo.txt"
    if not path.is_file():
        return list(_SI_MARK_FALLBACK)
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        if line or lines:
            lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines or list(_SI_MARK_FALLBACK)


def side_by_side(
    left: list[str],
    right: list[str],
    *,
    gap: int = 4,
) -> list[str]:
    """Fastfetch-style: art on the left, text on the right."""
    left_plain = [re.sub(r"\033\[[0-9;]*m", "", ln) for ln in left]
    left_w = max((len(ln) for ln in left_plain), default=0)
    height = max(len(left), len(right))
    out: list[str] = []
    for i in range(height):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        pad = max(0, left_w - _visible_len(l))
        out.append(l + " " * (pad + gap) + r)
    return out


def strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def si_logo_colored(*, color: bool = True) -> list[str]:
    if color:
        return [c(line, _RED, _BOLD, color=True) for line in load_si_logo()]
    return load_si_logo()


def format_version_card(data: dict, *, color: bool = True) -> str:
    """SI logo left, app version info right."""
    logo = si_logo_colored(color=color)
    name = data.get("name") or "System Inspector"
    version = data.get("version") or "—"
    cli = data.get("cli") or "si · sysinspect"
    info = [
        c(name, _BOLD, _WHITE, color=color),
        c("Version", _DIM, color=color) + f"  {version}",
        c("CLI", _DIM, color=color) + f"       {cli}",
        c("local · offline · no server", _DIM, color=color),
    ]
    return "\n".join(side_by_side(logo, info, gap=4))


def banner(color: bool = True) -> str:
    """SI logo left, taglines right — only for bare `si` and `si help`."""
    logo = si_logo_colored(color=color)
    tag = [
        c("SYSTEM INSPECTOR", _BOLD, _WHITE, color=color)
        + c("  ·  local live vitals and hardware", _DIM, color=color),
        c("· offline · Ctrl+C stops live", _DIM, color=color),
    ]
    body = side_by_side(logo, tag, gap=4)
    sep = c("─" * min(72, max(40, term_width() - 2)), _DIM, color=color)
    return "\n".join(body + ["", sep])


def format_os_card(data: dict, *, color: bool = True) -> str:
    """Distro logo left, OS facts right."""
    from backend.art.os_logos import distro_logo

    key, art, from_ff = distro_logo(data)
    if from_ff:
        logo = art if color else [strip_ansi(line) for line in art]
    else:
        logo = [c(line, _DIM, color=color) for line in art]

    os_name = data.get("pretty_name") or data.get("name") or "—"
    info = [
        c("OS", _DIM, color=color) + f"       {os_name}",
        c("Kernel", _DIM, color=color) + f"   {data.get('kernel') or data.get('release') or '—'}",
        c("Host", _DIM, color=color) + f"     {data.get('hostname') or '—'}",
        c("Desktop", _DIM, color=color)
        + f"  {data.get('desktop_environment') or '—'}  ·  {data.get('session_type') or '—'}",
        c("Arch", _DIM, color=color) + f"     {data.get('architecture') or '—'}",
    ]
    if from_ff and not color:
        info = [strip_ansi(line) if isinstance(line, str) else line for line in info]
    body = side_by_side(logo, info, gap=4)
    return "\n".join(body)



def term_width() -> int:
    try:
        return max(40, shutil.get_terminal_size((80, 24)).columns)
    except OSError:
        return 80


def term_height() -> int:
    try:
        return max(20, shutil.get_terminal_size((80, 24)).lines)
    except OSError:
        return 30


def _sev_style_battery(v: float, *, plugged: bool) -> tuple[str, ...]:
    if plugged:
        return (_GRN,)
    if v <= 10:
        return (_BOLD, _RED)
    if v <= 25:
        return (_BOLD, _YEL)
    return (_GRN,)


def _sev_style(v: float, *, hot: bool = False) -> tuple[str, ...]:
    """Color for severity: green → white → yellow → red."""
    if hot:
        # temperatures (°C) mapped roughly
        if v >= 85:
            return (_BOLD, _RED)
        if v >= 70:
            return (_BOLD, _YEL)
        if v >= 50:
            return (_WHITE,)
        return (_GRN,)
    # percentages
    if v >= 90:
        return (_BOLD, _RED)
    if v >= 70:
        return (_BOLD, _YEL)
    if v >= 35:
        return (_WHITE,)
    return (_GRN,)


def default_bar_width(*, columns: int = 1) -> int:
    """Use nearly the full terminal width — sparse bars feel 'small'."""
    cols = max(1, columns)
    # "    load  " (~10) + value (~8) + gutters between columns
    chrome = 18 + (8 if cols > 1 else 0)
    usable = max(40, term_width() - 2) // cols
    return max(28 if cols > 1 else 36, usable - chrome)


def meter(
    value: float | None,
    width: int | None = None,
    color: bool = True,
    *,
    unit: str = "%",
    label: str | None = None,
) -> str:
    """Unicode block bar for 0–100 with a bold, high-contrast value."""
    if width is None:
        width = default_bar_width()
    if value is None:
        empty = "─" * width
        tail = f"  {label}" if label else f"  n/a"
        return c(f"[{empty}]", _DIM, color=color) + c(tail, _DIM, color=color)
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return meter(None, width=width, color=color, unit=unit, label=label)
    filled = int(round((v / 100.0) * width))
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    if label is not None:
        value_txt = label
    elif unit == "%":
        value_txt = f"{int(round(v)):>3}%"
    else:
        value_txt = f"{int(round(v))}{unit}"
    bar_s = c(f"[{bar}]", *_sev_style(v, hot=(unit == "°C")), color=color)
    val_s = c(f" {value_txt}", _BOLD, *_sev_style(v, hot=(unit == "°C")), color=color)
    return bar_s + val_s


def temp_meter(
    celsius: float | None,
    width: int | None = None,
    color: bool = True,
    lo: float = 25,
    hi: float = 100,
) -> str:
    """Map temperature into a bar on a fixed 25–100°C scale."""
    if width is None:
        width = default_bar_width()
    if celsius is None:
        return meter(None, width=width, color=color, unit="°C")
    try:
        t = float(celsius)
    except (TypeError, ValueError):
        return meter(None, width=width, color=color, unit="°C")
    pct = (t - lo) / (hi - lo) * 100.0
    return meter(pct, width=width, color=color, unit="°C", label=f"{int(round(t)):>3}°C")


def decorate_human(text: str, color: bool = True) -> str:
    """
    Post-process plain human output: add big meters next to Load / % / temps.
    """
    w = max(24, min(48, term_width() - 22))
    out_lines: list[str] = []
    for line in text.splitlines():
        # CPU Load   10%
        m = re.match(r"^(\s*Load\s+)(\d+)%(\s*)$", line)
        if m:
            out_lines.append(f"{m.group(1)}{meter(float(m.group(2)), width=w, color=color)}")
            continue
        m = re.match(r"^(\s*Memory\s+)(\d+)%(.*)$", line)
        if m:
            out_lines.append(
                f"{m.group(1)}{meter(float(m.group(2)), width=w, color=color)}{m.group(3)}"
            )
            continue
        # Live  CPU 10%  ·  GPU 0%  ·  RAM 60%
        if line.startswith("Live  ") and "%" in line:
            parts = line.replace("Live  ", "", 1)
            chunks = [p.strip() for p in parts.split("·")]
            rebuilt = []
            for ch in chunks:
                mm = re.match(r"^(CPU|GPU|RAM)\s+(\d+)%$", ch.strip())
                if mm:
                    rebuilt.append(
                        f"{mm.group(1)} {meter(float(mm.group(2)), width=max(12, w - 6), color=color)}"
                    )
                else:
                    rebuilt.append(ch)
            out_lines.append("Live  " + "  ·  ".join(rebuilt))
            continue
        m = re.match(r"^(\s+Load\s+)(\d+)%(.*)$", line)
        if m:
            out_lines.append(
                f"{m.group(1)}{meter(float(m.group(2)), width=max(14, w - 4), color=color)}{m.group(3)}"
            )
            continue
        # "  name   34°C" GPU temp lines
        m = re.match(r"^(\s+.+\s+)(\d+)°C\s*$", line)
        if m and "Temp" not in m.group(1) and "CPU temp" not in m.group(1):
            # only decorate short temp-only lines
            if len(m.group(1)) < 45:
                out_lines.append(
                    f"{m.group(1).rstrip()}  {temp_meter(float(m.group(2)), width=max(14, w - 4), color=color)}"
                )
                continue
        m = re.match(r"^(\s*Temp\s+)(\d+)°C\s*$", line)
        if m:
            out_lines.append(
                f"{m.group(1)}{temp_meter(float(m.group(2)), width=max(14, w - 4), color=color)}"
            )
            continue
        m = re.match(r"^(\s*Swap\s+)(\d+)%(.*)$", line)
        if m:
            out_lines.append(
                f"{m.group(1)}{meter(float(m.group(2)), width=w, color=color)}{m.group(3)}"
            )
            continue
        # CPU 45°C  (si temps)
        m = re.match(r"^(CPU\s+)(\d+)°C\s*$", line)
        if m:
            out_lines.append(
                f"{m.group(1)}{temp_meter(float(m.group(2)), width=max(14, w - 4), color=color)}"
            )
            continue
        # GPU name  45°C  (si temps)
        m = re.match(r"^(GPU\s+.+?\s+)(\d+)°C\s*$", line)
        if m:
            out_lines.append(
                f"{m.group(1).rstrip()}  {temp_meter(float(m.group(2)), width=max(14, w - 4), color=color)}"
            )
            continue
        # Temps  CPU 45°C  ·  GPU 50°C  (si status)
        if line.startswith("Temps  ") and "°C" in line:
            parts = line.replace("Temps  ", "", 1)
            chunks = [p.strip() for p in parts.split("·")]
            rebuilt = []
            for ch in chunks:
                mm = re.match(r"^(CPU|GPU)\s+(\d+)°C$", ch.strip())
                if mm:
                    rebuilt.append(
                        f"{mm.group(1)} {temp_meter(float(mm.group(2)), width=max(10, w - 8), color=color)}"
                    )
                else:
                    rebuilt.append(ch)
            out_lines.append("Temps  " + "  ·  ".join(rebuilt))
            continue
        # Disk partition fill:   /home  72%  ·  10/50 GB
        m = re.match(r"^(\s+\S+\s+)(\d+(?:\.\d+)?)%(.*)$", line)
        if m and "·" in line and "GB" in line:
            pct = float(m.group(2))
            out_lines.append(
                f"{m.group(1)}{meter(pct, width=max(14, w - 4), color=color, label=f'{int(round(pct))}%')}{m.group(3)}"
            )
            continue
        # Fan duty %
        m = re.match(r"^(\s+.+?\s+)(\d+)%\s*$", line)
        if m and "Load" not in line and "Memory" not in line and "Swap" not in line:
            pct = float(m.group(2))
            style = _sev_style(pct) if pct < 90 else (_BOLD, _YEL)
            bar_w = max(14, w - 4)
            filled = int(round((pct / 100.0) * bar_w))
            bar = "█" * filled + "░" * (bar_w - filled)
            out_lines.append(
                f"{m.group(1)}"
                + c(f"[{bar}]", *style, color=color)
                + c(f" {int(round(pct)):>3}%", _BOLD, *style, color=color)
            )
            continue
        # CPU load  50%  ·  load1 …
        m = re.match(r"^(CPU load\s+)(\d+)%(.*)$", line)
        if m:
            out_lines.append(
                f"{m.group(1)}{meter(float(m.group(2)), width=w, color=color)}{m.group(3)}"
            )
            continue
        m = re.match(r"^(CPU temp\s+)(\d+)°C\s*$", line)
        if m:
            out_lines.append(f"{m.group(1)}{temp_meter(float(m.group(2)), width=w, color=color)}")
            continue
        # Battery  80%  ·  AC  (inverted: low charge is bad)
        m = re.match(r"^(Battery\s+)(\d+(?:\.\d+)?)%(.*)$", line)
        if m:
            pct = float(m.group(2))
            plugged = "AC" in m.group(3)
            bar_w = w
            filled = int(round((pct / 100.0) * bar_w))
            bar = "█" * filled + "░" * (bar_w - filled)
            style = _sev_style_battery(pct, plugged=plugged)
            out_lines.append(
                f"{m.group(1)}"
                + c(f"[{bar}]", *style, color=color)
                + c(f" {int(round(pct)):>3}%", _BOLD, *style, color=color)
                + m.group(3)
            )
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------- watch dashboard (compact, monitor-friendly) ----------


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_metrics(payload: dict) -> list[dict[str, Any]]:
    """
    Flatten any payload into monitor rows:
      {key, label, pct, temp_c, extra, unit_kind}
    Used by watch view + graph.
    """
    rows: list[dict[str, Any]] = []
    if not payload.get("ok"):
        return rows

    r = payload.get("resource")
    d = payload.get("data") or {}
    fields = set(payload.get("fields") or [])

    if r == "bundle":
        for part in payload.get("results") or []:
            rows.extend(extract_metrics(part))
        # de-dupe by key (cpu+temps both emit CPU temp)
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            k = row["key"]
            if k in seen:
                # merge temp/pct into existing
                for prev in out:
                    if prev["key"] == k:
                        if prev.get("pct") is None and row.get("pct") is not None:
                            prev["pct"] = row["pct"]
                        if prev.get("temp_c") is None and row.get("temp_c") is not None:
                            prev["temp_c"] = row["temp_c"]
                        if row.get("extra") and not prev.get("extra"):
                            prev["extra"] = row["extra"]
                        break
                continue
            seen.add(k)
            out.append(row)
        return out

    want_temp = not fields or "temp" in fields or r in ("temps",)
    want_usage = not fields or "usage" in fields or r not in ("temps",)
    if fields == {"temp"}:
        want_usage = False
    if fields == {"usage"}:
        want_temp = False
    if r == "temps":
        want_usage = False
        want_temp = True

    if r == "cpu":
        rows.append(
            {
                "key": "cpu",
                "label": "CPU",
                "pct": _f(d.get("usage_percent")) if want_usage else None,
                "temp_c": _f(d.get("temp_c")) if want_temp else None,
                "extra": (
                    f"{d.get('freq_current_mhz') or 'n/a'} MHz" if not fields else None
                ),
                "note": d.get("note"),
            }
        )
        return rows

    if r == "gpu":
        for i, g in enumerate(d.get("devices") or []):
            name = (g.get("name") or f"GPU{i}")[:28]
            extra = None
            if g.get("power_watts") is not None:
                extra = f"{g.get('power_watts')} W"
            elif g.get("vram_used_mb") is not None and g.get("vram_total_mb") is not None:
                extra = f"VRAM {g.get('vram_used_mb')}/{g.get('vram_total_mb')} MB"
            pct = _f(g.get("usage_percent")) if want_usage else None
            temp = _f(g.get("temp_c")) if want_temp else None
            rows.append(
                {
                    "key": f"gpu{i}",
                    "label": name,
                    "pct": pct,
                    "temp_c": temp,
                    "extra": extra,
                    "note": g.get("note"),
                }
            )
        return rows

    if r == "temps":
        rows.append(
            {
                "key": "cpu",
                "label": "CPU",
                "pct": None,
                "temp_c": _f(d.get("cpu_c")),
                "extra": None,
                "note": None if d.get("cpu_c") is not None else "CPU temp not reported",
            }
        )
        for i, g in enumerate(d.get("gpus") or []):
            rows.append(
                {
                    "key": f"gpu{i}",
                    "label": (g.get("name") or f"GPU{i}")[:28],
                    "pct": None,
                    "temp_c": _f(g.get("temp_c")),
                    "extra": None,
                    "note": g.get("note")
                    or (
                        None
                        if g.get("temp_c") is not None
                        else "GPU temp not reported"
                    ),
                }
            )
        return rows

    if r == "memory":
        ram = d.get("ram") or d
        rows.append(
            {
                "key": "ram",
                "label": "RAM",
                "pct": _f(ram.get("percent")),
                "temp_c": None,
                "extra": f"{ram.get('used_gb')}/{ram.get('total_gb')} GB",
            }
        )
        return rows

    if r == "status":
        live = d.get("live") or {}
        rows.append(
            {
                "key": "cpu",
                "label": "CPU",
                "pct": _f(live.get("cpu_percent")),
                "temp_c": _f(live.get("cpu_temp_c")),
                "extra": None,
            }
        )
        rows.append(
            {
                "key": "gpu0",
                "label": "GPU",
                "pct": _f(live.get("gpu_percent")),
                "temp_c": _f(live.get("gpu_temp_c")),
                "extra": None,
                "note": live.get("gpu_note"),
            }
        )
        rows.append(
            {
                "key": "ram",
                "label": "RAM",
                "pct": _f(live.get("ram_percent")),
                "temp_c": None,
                "extra": None,
            }
        )
        return rows

    if r == "disk":
        rates = d.get("rates_mbs") or {}
        rows.append(
            {
                "key": "disk_r",
                "label": "Disk read",
                "pct": None,
                "temp_c": None,
                "extra": f"{rates.get('read') or 0} MB/s",
                "rate": _f(rates.get("read")),
            }
        )
        rows.append(
            {
                "key": "disk_w",
                "label": "Disk write",
                "pct": None,
                "temp_c": None,
                "extra": f"{rates.get('write') or 0} MB/s",
                "rate": _f(rates.get("write")),
            }
        )
        return rows

    if r == "net":
        # Slices like connections/listen use format_human (colored rows), not throughput bars.
        if fields.intersection(
            {
                "connections",
                "listen",
                "routes",
                "gateway",
                "dns",
                "wifi",
                "public",
                "ip",
                "interfaces",
            }
        ):
            return []
        rates = d.get("rates_mbs") or {}
        rows.append(
            {
                "key": "net_rx",
                "label": "Net ↓",
                "pct": None,
                "temp_c": None,
                "extra": f"{rates.get('recv') or 0} MB/s",
                "rate": _f(rates.get("recv")),
            }
        )
        rows.append(
            {
                "key": "net_tx",
                "label": "Net ↑",
                "pct": None,
                "temp_c": None,
                "extra": f"{rates.get('sent') or 0} MB/s",
                "rate": _f(rates.get("sent")),
            }
        )
        return rows

    if r == "fans":
        for i, f in enumerate(d.get("fans") or []):
            label = (f.get("label") or f.get("sensor") or f"fan{i}")[:28]
            if f.get("percent") is not None:
                rows.append(
                    {
                        "key": f"fan{i}",
                        "label": label,
                        "pct": _f(f.get("percent")),
                        "temp_c": None,
                        "extra": None,
                    }
                )
            elif f.get("rpm") is not None:
                rows.append(
                    {
                        "key": f"fan{i}",
                        "label": label,
                        "pct": None,
                        "temp_c": None,
                        "extra": f"{f.get('rpm')} RPM",
                    }
                )
        return rows

    if r == "battery":
        if d.get("present"):
            rows.append(
                {
                    "key": "bat",
                    "label": "Battery",
                    "pct": _f(d.get("percent")),
                    "temp_c": None,
                    "extra": "AC" if d.get("power_plugged") else "on battery",
                }
            )
        return rows

    return rows


def _sensor_block(row: dict[str, Any], w_bar: int, color: bool) -> list[str]:
    """One sensor's lines for the live board (no trailing blank)."""
    lines: list[str] = []
    title = row["label"]
    if row.get("extra") and row.get("pct") is None and row.get("temp_c") is None:
        title = f"{title}  ·  {row['extra']}"
    lines.append(c(f"  {title}", _BOLD, _WHITE, color=color))

    has_pct = row.get("pct") is not None
    has_temp = row.get("temp_c") is not None
    has_rate = row.get("rate") is not None
    note = row.get("note")

    if has_pct:
        lines.append(
            "    "
            + c("load  ", _DIM, color=color)
            + meter(row.get("pct"), width=w_bar, color=color)
        )
    if has_temp:
        lines.append(
            "    "
            + c("temp  ", _DIM, color=color)
            + temp_meter(row.get("temp_c"), width=w_bar, color=color)
        )
    if has_rate and not has_pct:
        rate = float(row.get("rate") or 0.0)
        pct_vis = min(100.0, (rate / 500.0) * 100.0)
        lines.append(
            "    "
            + c("rate  ", _DIM, color=color)
            + meter(
                pct_vis,
                width=w_bar,
                color=color,
                unit="",
                label=f"{rate:.1f} MB/s",
            )
        )
    if row.get("extra") and has_pct:
        lines.append(c(f"          {row['extra']}", _DIM, color=color))
    if not has_pct and not has_temp and not has_rate:
        # Prefer a clear sentence over a hollow bar of dashes
        if note:
            lines.append(c(f"    {note}", _DIM, color=color))
        else:
            lines.append(
                "    "
                + c("      ", _DIM, color=color)
                + meter(None, width=w_bar, color=color, unit="", label="n/a")
            )
    elif note and (not has_pct or not has_temp):
        lines.append(c(f"    {note}", _DIM, color=color))
    return lines


def _pad_block(block: list[str], height: int) -> list[str]:
    out = list(block)
    while len(out) < height:
        out.append("")
    return out


def format_watch_dashboard(payload: dict, color: bool = True) -> str:
    """
    Live board of block bars. Dense by default; two columns on wide terminals.
    """
    rows = extract_metrics(payload)
    if not rows:
        from backend.format import format_human

        return decorate_human(format_human(payload, color=color), color=color)

    tw = term_width()
    columns = 2 if tw >= 100 and len(rows) >= 2 else 1
    w_bar = default_bar_width(columns=columns)
    blocks = [_sensor_block(row, w_bar, color) for row in rows]

    if columns == 1:
        # Tight stack: one blank only between sensors (not after the last)
        lines: list[str] = []
        for i, block in enumerate(blocks):
            if i:
                lines.append("")
            lines.extend(block)
        return "\n".join(lines)

    # Two-column: pair sensors side by side
    col_w = max(40, (tw - 2) // 2)
    lines = []
    for i in range(0, len(blocks), 2):
        left = blocks[i]
        right = blocks[i + 1] if i + 1 < len(blocks) else []
        h = max(len(left), len(right), 1)
        left = _pad_block(left, h)
        right = _pad_block(right, h)
        if i:
            lines.append("")
        for a, b in zip(left, right):
            pad = max(1, col_w - _visible_len(a))
            if right and any(right):
                lines.append(a + (" " * pad) + b)
            else:
                lines.append(a)
    return "\n".join(lines)


# Words people can type while live — same vocabulary as `si …`
LIVE_TYPE_HINT = "cpu  gpu  ram  temps  disk  net  fans  battery"

LIVE_HELP_LINES = (
    "type a word, then Enter — same as si:",
    LIVE_TYPE_HINT,
    "status / clear → overview",
    "quit → leave   ·   graph → charts   ·   faster / slower → refresh",
    "Esc clears typing   ·   Ctrl+C also quits",
)


def live_help_flash() -> str:
    """Help shown only when the user asks (? or help) — not on every frame."""
    return "\n".join(LIVE_HELP_LINES)


def live_chrome(
    *,
    watching: str,
    interval: float,
    draft: str,
    flash: str = "",
    graph: bool = False,
    refresh_slow: bool = False,
    color: bool = True,
) -> str:
    """Minimal footer: status + prompt. Help only appears in flash (?)."""
    watch = watching or "status"
    graph_s = "on" if graph else "off"
    slow_s = "  ·  refresh slow" if refresh_slow else ""
    lines = [
        c("  " + "─" * min(52, max(36, term_width() - 4)), _DIM, color=color),
        c(f"  watching  {watch}", _BOLD, _WHITE, color=color)
        + c(f"  ·  {interval:g}s  ·  charts {graph_s}{slow_s}  ·  ? help", _DIM, color=color),
        c("  › ", _BOLD, _RED, color=color)
        + c(draft, _WHITE, color=color)
        + c("█", _DIM, color=color),
    ]
    if flash:
        # Allow multi-line help without permanently eating vertical space
        for i, part in enumerate(flash.split("\n")):
            lines.insert(1 + i, c(f"  {part}", _BOLD, _YEL if i == 0 else _DIM, color=color))
    return "\n".join(lines)


def enter_alt_screen() -> None:
    sys.stdout.write("\033[?1049h\033[H\033[?25l")
    sys.stdout.flush()


def leave_alt_screen() -> None:
    sys.stdout.write("\033[?25h\033[?1049l")
    sys.stdout.flush()


def clear_home() -> None:
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()


# ---------- live graph ----------


SeriesPoint = tuple[str, float | None, Literal["pct", "temp", "rate"]]


def extract_plot_series(payload: dict) -> list[SeriesPoint]:
    """Pull (name, value, unit) points for live graphing — units stay separated."""
    series: list[SeriesPoint] = []
    for row in extract_metrics(payload):
        label = row["label"]
        if row.get("pct") is not None:
            series.append((f"{label} %", row["pct"], "pct"))
        if row.get("temp_c") is not None:
            series.append((f"{label} °C", row["temp_c"], "temp"))
        if row.get("rate") is not None:
            series.append((f"{label}", row["rate"], "rate"))
    return series


class LiveHistory:
    def __init__(self, maxlen: int = 90) -> None:
        self.maxlen = maxlen
        # name -> (unit, deque)
        self.series: dict[str, tuple[str, collections.deque[float]]] = {}
        self._active: set[str] = set()

    def push(self, points: list[SeriesPoint]) -> None:
        seen: set[str] = set()
        for name, val, unit in points:
            seen.add(name)
            if name not in self.series:
                self.series[name] = (unit, collections.deque(maxlen=self.maxlen))
            else:
                # keep unit from first sight
                unit = self.series[name][0]
            if val is None:
                continue
            try:
                self.series[name][1].append(float(val))
            except (TypeError, ValueError):
                continue
        for k in list(self.series.keys()):
            if k not in seen:
                del self.series[k]
        self._active = seen

    def nonempty(self) -> bool:
        return any(len(dq) > 0 for _, dq in self.series.values())

    def by_unit(self, unit: str) -> dict[str, collections.deque[float]]:
        return {n: dq for n, (u, dq) in self.series.items() if u == unit and dq}


def render_graph(history: LiveHistory, title: str, color: bool = True) -> str:
    """
    Live charts with *fixed* scales so a flat line means quiet, not broken axis.
      load  → y 0..100 %
      temps → y 20..100 °C
      rates → auto with floor
    Draws two (or three) stacked panels so different units never share a Y axis.
    """
    if not history.nonempty():
        return c("  (graph: collecting samples…)", _DIM, color=color)

    panels: list[tuple[str, dict[str, collections.deque[float]], tuple[float, float] | None]] = []
    pct = history.by_unit("pct")
    temp = history.by_unit("temp")
    rate = history.by_unit("rate")
    if pct:
        panels.append(("utilization %", pct, (0.0, 100.0)))
    if temp:
        panels.append(("temperature °C", temp, (20.0, 100.0)))
    if rate:
        panels.append(("throughput MB/s", rate, None))

    if not panels:
        return c("  (graph: no numeric series yet)", _DIM, color=color)

    blocks: list[str] = []
    try:
        import plotext as plt  # type: ignore
    except ImportError:
        return _spark_fallback(history, title, color=color)

    width = max(60, min(term_width() - 2, 120))
    # leave room for banner + meters; bigger than the old 18-row single plot
    avail = max(16, term_height() - 14)
    height_each = max(10, min(16, avail // max(1, len(panels))))

    palette = ["red+", "orange+", "tomato+", "cyan+", "white+", "yellow+", "green+"]

    for panel_title, data_map, ylim in panels:
        plt.clear_figure()
        plt.plotsize(width, height_each)
        plt.title(f"{title} · {panel_title}")
        try:
            plt.theme("dark" if color else "clear")
        except Exception:
            pass
        if ylim is not None:
            try:
                plt.ylim(ylim[0], ylim[1])
            except Exception:
                pass
        i = 0
        any_plotted = False
        for name, dq in data_map.items():
            if len(dq) < 1:
                continue
            vals = list(dq)
            # pad short series so plotext has an x range
            if len(vals) == 1:
                vals = vals + vals
            try:
                plt.plot(vals, label=name[:20], marker="braille", color=palette[i % len(palette)])
                any_plotted = True
            except Exception:
                try:
                    plt.plot(vals, label=name[:20])
                    any_plotted = True
                except Exception:
                    pass
            i += 1
        if not any_plotted:
            continue
        try:
            plt.xlabel("samples →")
        except Exception:
            pass
        try:
            built = plt.build()
        except Exception:
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                plt.show()
            built = buf.getvalue()
        blocks.append(built.rstrip())

    if not blocks:
        return _spark_fallback(history, title, color=color)
    return "\n\n".join(blocks)


def _spark_fallback(history: LiveHistory, title: str, color: bool = True) -> str:
    """Fixed-scale sparklines (no plotext). Y scale is stable so motion is real."""
    blocks = " ▁▂▃▄▅▆▇█"
    lines = [
        c(f"  {title}", _BOLD, color=color),
        c("  (pip install plotext → fuller charts; these sparklines use fixed scales)", _DIM, color=color),
    ]

    def spark(vals: list[float], lo: float, hi: float) -> str:
        span = (hi - lo) or 1.0
        out = []
        for v in vals[-min(60, max(10, term_width() - 30)) :]:
            t = (v - lo) / span
            t = max(0.0, min(1.0, t))
            out.append(blocks[min(8, int(t * 8))])
        return "".join(out)

    for unit, lo, hi, suffix in (
        ("pct", 0.0, 100.0, "%"),
        ("temp", 20.0, 100.0, "°C"),
        ("rate", 0.0, 100.0, " MB/s"),
    ):
        data = history.by_unit(unit)
        if not data:
            continue
        lines.append(c(f"  ── {unit} ({lo:g}–{hi:g}{suffix}) ──", _DIM, color=color))
        for name, dq in data.items():
            vals = list(dq)
            if not vals:
                continue
            # rates: auto hi
            use_hi = hi
            use_lo = lo
            if unit == "rate":
                use_hi = max(10.0, max(vals) * 1.25)
            last = vals[-1]
            bar = spark(vals, use_lo, use_hi)
            lines.append(
                f"  {name[:18]:18} {bar}  "
                + c(f"{last:.1f}{suffix if unit != 'rate' else ' MB/s'}", _BOLD, color=color)
            )
    return "\n".join(lines)
