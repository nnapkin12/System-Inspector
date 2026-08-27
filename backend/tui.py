"""
Terminal chrome for System Inspector CLI: banner, meters, live charts.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Any, Literal

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
    "   ████████                         ████████",
    "  ██     ██                            ██",
    " ██                                    ██",
    " ██                                    ██",
    "  █████████                            ██",
    "         ██                            ██",
    "         ██                            ██",
    "  ██     ██                            ██",
    "   ████████   SYSTEM                ████████ INSPECT",
]


def _visible_len(s: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _fit_line(s: str, width: int) -> str:
    """Keep one terminal row: strip ANSI for width, never wrap."""
    if width < 1:
        return ""
    if _visible_len(s) <= width:
        return s
    out: list[str] = []
    vis = 0
    i = 0
    while i < len(s) and vis < width:
        if s[i] == "\033":
            m = re.match(r"\033\[[0-9;]*m", s[i:])
            if m:
                out.append(m.group(0))
                i += len(m.group(0))
                continue
        out.append(s[i])
        vis += 1
        i += 1
    out.append(_RESET)
    return "".join(out)


def load_si_logo() -> list[str]:
    path = Path(__file__).resolve().parent / "art" / "logo.txt"
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


def logo_header(*, watching: str = "", facts: list[str] | None = None, color: bool = True) -> str:
    """SI wordmark left (S and I already in the art). Facts sit lower so the I cap is not clipped."""
    logo = si_logo_colored(color=color)
    right: list[str] = [""]
    right.append(c("SYSTEM INSPECTOR", _BOLD, _WHITE, color=color))
    if watching:
        right.append(c(watching, _DIM, color=color))
    else:
        right.append(c("local · offline · no server", _DIM, color=color))
    if facts:
        right.append("")
        right.extend(facts)
    return "\n".join(side_by_side(logo, right, gap=3))


def status_identity_lines(data: dict, *, color: bool = True, width: int | None = None) -> list[str]:
    """Hardware names + uptime beside the logo — no OS / host."""
    from backend.format import fmt_uptime, short_gpu

    logo_w = max((len(ln) for ln in load_si_logo()), default=0) + 3
    name_w = max(18, (width or term_width()) - logo_w - 6)

    cpu = data.get("cpu") or "—"
    if len(str(cpu)) > name_w:
        cpu = str(cpu)[: max(8, name_w - 1)] + "…"
    gpus = data.get("gpus") or []
    gpu = short_gpu(gpus[0]) if gpus else "—"
    if gpu.lower().startswith("nvidia "):
        gpu = gpu[7:]
    if len(gpus) > 1:
        gpu = f"{gpu}  + iGPU"
    if len(gpu) > name_w:
        gpu = gpu[: max(8, name_w - 1)] + "…"
    return [
        c("CPU", _DIM, color=color) + f"  {cpu}",
        c("GPU", _DIM, color=color) + f"  {gpu}",
        c("up ", _DIM, color=color) + f" {fmt_uptime(data.get('uptime_seconds'))}",
    ]


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
    """Green = healthy/low, yellow = mid, red = high. No white mid-band."""
    if hot:
        if v >= 83:
            return (_BOLD, _RED)
        if v >= 65:
            return (_BOLD, _YEL)
        return (_GRN,)
    if v >= 80:
        return (_BOLD, _RED)
    if v >= 55:
        return (_BOLD, _YEL)
    return (_GRN,)


def _painted_bar(filled: int, width: int, style: tuple[str, ...], *, color: bool) -> str:
    """Colored fill, dim empty — the whole bar no longer flashes white."""
    filled = max(0, min(width, filled))
    fill = c("█" * filled, *style, color=color)
    empty = c("░" * (width - filled), _DIM, color=color)
    return c("[", _DIM, color=color) + fill + empty + c("]", _DIM, color=color)


def default_bar_width(*, columns: int = 1) -> int:
    """Bar body so `    [bar]` always fits on one row."""
    cols = max(1, columns)
    tw = term_width()
    indent_and_brackets = 6  # four spaces + [ ]
    if cols == 1:
        return max(8, tw - indent_and_brackets)
    col_w = max(24, (tw - 2) // cols)
    return max(8, col_w - indent_and_brackets)


def bar_thickness() -> int:
    """Two-row bars when the terminal is tall enough; one row on short windows."""
    return 2 if term_height() >= 28 else 1


def meter(
    value: float | None,
    width: int | None = None,
    color: bool = True,
    *,
    unit: str = "%",
    label: str | None = None,
    severity: float | None = None,
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
        return meter(None, width=width, color=color, unit=unit, label=label, severity=severity)
    filled = int(round((v / 100.0) * width))
    filled = max(0, min(width, filled))
    if label is not None:
        value_txt = label
    elif unit == "%":
        value_txt = f"{int(round(v)):>3}%"
    else:
        value_txt = f"{int(round(v))}{unit}"
    hot = unit == "°C"
    try:
        sev = float(severity) if severity is not None else v
    except (TypeError, ValueError):
        sev = v
    style = _sev_style(sev, hot=hot)
    bar_s = _painted_bar(filled, width, style, color=color)
    val_s = c(f" {value_txt}", _BOLD, *style, color=color)
    return bar_s + val_s


def meter_block(
    value: float | None,
    width: int | None = None,
    color: bool = True,
    *,
    unit: str = "%",
    label: str | None = None,
    rows: int | None = None,
    severity: float | None = None,
) -> list[str]:
    """Big readout + 1–2 row bar for the live board."""
    if width is None:
        width = default_bar_width()
    if rows is None:
        rows = bar_thickness()
    rows = max(1, min(3, rows))
    if value is None:
        empty = "─" * width
        tail = label if label else "n/a"
        bar = c(f"    [{empty}]", _DIM, color=color)
        return [c(f"    {tail}", _DIM, color=color)] + [bar] * rows
    try:
        v = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return meter_block(
            None, width=width, color=color, unit=unit, label=label, rows=rows, severity=severity
        )
    filled = int(round((v / 100.0) * width))
    filled = max(0, min(width, filled))
    if label is not None:
        value_txt = label
    elif unit == "%":
        value_txt = f"{int(round(v))}%"
    else:
        value_txt = f"{int(round(v))}{unit}"
    hot = unit == "°C"
    try:
        sev = float(severity) if severity is not None else v
    except (TypeError, ValueError):
        sev = v
    style = _sev_style(sev, hot=hot)
    out = [c(f"    {value_txt}", _BOLD, *style, color=color)]
    bar_line = "    " + _painted_bar(filled, width, style, color=color)
    out.extend([bar_line] * rows)
    return out


def temp_meter_block(
    celsius: float | None,
    width: int | None = None,
    color: bool = True,
    lo: float = 25,
    hi: float = 100,
    rows: int | None = None,
) -> list[str]:
    if celsius is None:
        return meter_block(None, width=width, color=color, unit="°C", rows=rows)
    try:
        t = float(celsius)
    except (TypeError, ValueError):
        return meter_block(None, width=width, color=color, unit="°C", rows=rows)
    pct = (t - lo) / (hi - lo) * 100.0
    return meter_block(
        pct,
        width=width,
        color=color,
        unit="°C",
        label=f"{int(round(t))}°C",
        rows=rows,
        severity=t,
    )


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
    return meter(
        pct, width=width, color=color, unit="°C", label=f"{int(round(t)):>3}°C", severity=t
    )


def decorate_human(text: str, color: bool = True) -> str:
    """
    Post-process plain human output: add big meters next to Load / % / temps.
    """
    w = max(36, term_width() - 22)
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
            out_lines.append(
                f"{m.group(1)}"
                + _painted_bar(filled, bar_w, style, color=color)
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
            style = _sev_style_battery(pct, plugged=plugged)
            out_lines.append(
                f"{m.group(1)}"
                + _painted_bar(filled, bar_w, style, color=color)
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
        gpu_names = {(g.get("name") or "").lower() for g in (d.get("gpus") or [])}
        from backend.format import _is_cpu_or_gpu_temp_label

        extra_i = 0
        for s in d.get("all_sensors") or []:
            label = (s.get("label") or s.get("sensor") or "sensor").strip()
            if _is_cpu_or_gpu_temp_label(label, gpu_names):
                continue
            temp = _f(s.get("celsius"))
            if temp is None:
                continue
            rows.append(
                {
                    "key": f"hw{extra_i}",
                    "label": label[:28],
                    "pct": None,
                    "temp_c": temp,
                    "extra": None,
                }
            )
            extra_i += 1
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
        cpu_bits = []
        if live.get("cpu_freq_mhz") is not None:
            cpu_bits.append(f"{int(round(float(live['cpu_freq_mhz'])))} MHz")
        if live.get("load_1m") is not None:
            cpu_bits.append(f"load {live['load_1m']}")
        gpu_bits = []
        vu, vt = live.get("gpu_vram_used_mb"), live.get("gpu_vram_total_mb")
        if vu is not None and vt is not None:
            gpu_bits.append(f"{round(float(vu) / 1024, 1)}/{round(float(vt) / 1024, 1)} GB")
        if live.get("gpu_power_w") is not None:
            gpu_bits.append(f"{live['gpu_power_w']} W")
        ram_bits = []
        if live.get("ram_used_gb") is not None and live.get("ram_total_gb") is not None:
            ram_bits.append(f"{live['ram_used_gb']}/{live['ram_total_gb']} GB")
        rows.append(
            {
                "key": "cpu",
                "label": "CPU",
                "pct": _f(live.get("cpu_percent")),
                "temp_c": _f(live.get("cpu_temp_c")),
                "extra": "  ·  ".join(cpu_bits) or None,
            }
        )
        rows.append(
            {
                "key": "gpu0",
                "label": "GPU",
                "pct": _f(live.get("gpu_percent")),
                "temp_c": _f(live.get("gpu_temp_c")),
                "extra": "  ·  ".join(gpu_bits) or None,
                "note": live.get("gpu_note"),
            }
        )
        rows.append(
            {
                "key": "ram",
                "label": "RAM",
                "pct": _f(live.get("ram_percent")),
                "temp_c": None,
                "extra": "  ·  ".join(ram_bits) or None,
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
                "ping",
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
        nics = rates.get("per_nic") or []
        if len(nics) > 1:
            for nic in nics[:3]:
                name = nic.get("name") or "nic"
                rows.append(
                    {
                        "key": f"nic_{name}",
                        "label": name,
                        "pct": None,
                        "temp_c": None,
                        "extra": f"↓ {nic.get('recv') or 0}  ↑ {nic.get('sent') or 0} MB/s",
                        "rate": _f(nic.get("recv")),
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
    """One sensor for the live board: title, big number, thick bar."""
    lines: list[str] = []
    title = row["label"]
    if row.get("extra") and row.get("pct") is None and row.get("temp_c") is None:
        title = f"{title}  ·  {row['extra']}"
    lines.append(c(f"  {title}", _BOLD, _WHITE, color=color))

    has_pct = row.get("pct") is not None
    has_temp = row.get("temp_c") is not None
    has_rate = row.get("rate") is not None
    note = row.get("note")
    rows = bar_thickness()

    if has_pct:
        lines.append(c("    load", _DIM, color=color))
        lines.extend(meter_block(row.get("pct"), width=w_bar, color=color, rows=rows))
    if has_temp:
        lines.append(c("    temp", _DIM, color=color))
        lines.extend(temp_meter_block(row.get("temp_c"), width=w_bar, color=color, rows=rows))
    if has_rate and not has_pct:
        rate = float(row.get("rate") or 0.0)
        pct_vis = min(100.0, (rate / 500.0) * 100.0)
        lines.append(c("    rate", _DIM, color=color))
        lines.extend(
            meter_block(
                pct_vis,
                width=w_bar,
                color=color,
                unit="",
                label=f"{rate:.1f} MB/s",
                rows=rows,
            )
        )
    if row.get("extra") and has_pct:
        lines.append(c(f"    {row['extra']}", _DIM, color=color))
    if not has_pct and not has_temp and not has_rate:
        if note:
            lines.append(c(f"    {note}", _DIM, color=color))
        else:
            lines.extend(
                meter_block(None, width=w_bar, color=color, unit="", label="n/a", rows=rows)
            )
    elif note and (not has_pct or not has_temp):
        lines.append(c(f"    {note}", _DIM, color=color))
    return lines


def _pad_block(block: list[str], height: int) -> list[str]:
    out = list(block)
    while len(out) < height:
        out.append("")
    return out


def _fmt_rate(v: Any, *, ready: bool = True) -> str:
    if not ready or v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if n < 0.05:
        return "0.0"
    return f"{n:.1f}"


def _status_bar_rows() -> int:
    return 1


def format_status_board(payload: dict, color: bool = True) -> str:
    """Hardware vitals — full-width single-row bars, spaced sections."""
    live = (payload.get("data") or {}).get("live") or {}
    tw = term_width()
    w_bar = max(12, default_bar_width() - 8)
    rows = _status_bar_rows()
    gap = [""]
    sections: list[list[str]] = []

    def title(name: str, extra: str = "") -> list[str]:
        head = c(f"  {name}", _BOLD, _WHITE, color=color)
        if extra:
            head += c(f"  ·  {extra}", _DIM, color=color)
        return [head]

    cpu_bits = []
    if live.get("cpu_freq_mhz") is not None:
        cpu_bits.append(f"{float(live['cpu_freq_mhz']) / 1000:.1f} GHz")
    if live.get("load_1m") is not None:
        cpu_bits.append(f"load {live['load_1m']}")
    cpu = title("CPU", "  ·  ".join(cpu_bits))
    cpu.append(c("    load", _DIM, color=color))
    cpu.extend(meter_block(_f(live.get("cpu_percent")), width=w_bar, color=color, rows=rows))
    cpu.append(c("    temp", _DIM, color=color))
    cpu.extend(temp_meter_block(_f(live.get("cpu_temp_c")), width=w_bar, color=color, rows=rows))
    sections.append(cpu)

    gpu_bits = []
    if live.get("gpu_power_w") is not None:
        gpu_bits.append(f"{live['gpu_power_w']} W")
    if live.get("gpu_clock_mhz") is not None:
        gpu_bits.append(f"{int(round(float(live['gpu_clock_mhz'])))} MHz")
    gpu = title("GPU", "  ·  ".join(gpu_bits))
    if live.get("gpu_percent") is None and live.get("gpu_note"):
        gpu.append(c(f"    {live.get('gpu_note')}", _DIM, color=color))
    else:
        gpu.append(c("    load", _DIM, color=color))
        gpu.extend(meter_block(_f(live.get("gpu_percent")), width=w_bar, color=color, rows=rows))
    gpu.append(c("    temp", _DIM, color=color))
    gpu.extend(temp_meter_block(_f(live.get("gpu_temp_c")), width=w_bar, color=color, rows=rows))
    sections.append(gpu)

    ram_extra = ""
    if live.get("ram_used_gb") is not None and live.get("ram_total_gb") is not None:
        ram_extra = f"{live['ram_used_gb']} / {live['ram_total_gb']} GB"
    ram = title("RAM", ram_extra)
    ram.extend(meter_block(_f(live.get("ram_percent")), width=w_bar, color=color, rows=rows))
    sections.append(ram)

    vu, vt = _f(live.get("gpu_vram_used_mb")), _f(live.get("gpu_vram_total_mb"))
    if vu is not None and vt and vt > 0:
        vram = title("VRAM", f"{round(vu / 1024, 1)} / {round(vt / 1024, 1)} GB")
        vram.extend(meter_block(vu / vt * 100.0, width=w_bar, color=color, rows=rows))
        sections.append(vram)

    swap_pct = _f(live.get("swap_percent"))
    if swap_pct is not None and swap_pct > 0.5:
        swap_extra = ""
        if live.get("swap_used_gb") is not None and live.get("swap_total_gb") is not None:
            swap_extra = f"{live['swap_used_gb']} / {live['swap_total_gb']} GB"
        swap = title("SWAP", swap_extra)
        swap.extend(meter_block(swap_pct, width=w_bar, color=color, rows=rows))
        sections.append(swap)

    bat_pct = _f(live.get("battery_percent"))
    if bat_pct is not None:
        plugged = bool(live.get("battery_plugged"))
        plug = "AC" if plugged else "battery"
        style = _sev_style_battery(bat_pct, plugged=plugged)
        bat = title("BAT", plug)
        bat.append(c(f"    {int(round(bat_pct))}%", _BOLD, *style, color=color))
        filled = int(round((max(0.0, min(100.0, bat_pct)) / 100.0) * w_bar))
        bar_line = "    " + _painted_bar(filled, w_bar, style, color=color)
        bat.extend([bar_line] * rows)
        sections.append(bat)

    ready = bool(live.get("rates_ready"))
    io = title("NET")
    io.append(
        c(
            f"    ↓{_fmt_rate(live.get('net_recv_mbs'), ready=ready)}"
            f"  ↑{_fmt_rate(live.get('net_sent_mbs'), ready=ready)}  MB/s",
            _DIM,
            color=color,
        )
    )
    sections.append(io)

    lines: list[str] = []
    for i, block in enumerate(sections):
        if i:
            lines.extend(gap)
        lines.extend(block)
    return "\n".join(_fit_line(ln, tw) for ln in lines)


def format_watch_dashboard(payload: dict, color: bool = True) -> str:
    """
    Live board of block bars. Dense by default; two columns on wide terminals.
    """
    if payload.get("resource") == "status":
        return format_status_board(payload, color=color)

    rows = extract_metrics(payload)
    if not rows:
        from backend.format import format_human

        return decorate_human(format_human(payload, color=color), color=color)

    tw = term_width()
    # Two columns only on very wide terminals — splitting early makes bars tiny.
    columns = 2 if tw >= 160 and len(rows) >= 4 else 1
    w_bar = default_bar_width(columns=columns)
    blocks = [_sensor_block(row, w_bar, color) for row in rows]

    if columns == 1:
        # Tight stack: one blank only between sensors (not after the last)
        lines: list[str] = []
        for i, block in enumerate(blocks):
            if i:
                lines.append("")
            lines.extend(block)
        return "\n".join(_fit_line(ln, tw) for ln in lines)

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
    return "\n".join(_fit_line(ln, tw) for ln in lines)


# Words people can type while live — same vocabulary as `si …`
LIVE_TYPE_HINT = "cpu  gpu  ram  temps  disk  net  fans  battery"

LIVE_HELP_LINES = (
    "type a word, then Enter — same as si:",
    LIVE_TYPE_HINT,
    "status / clear → overview",
    "quit → leave   ·   graph cpu → plots   ·   bars → meters   ·   faster / slower",
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
    """Quiet footer for a rice pane. Prompt appears only while typing."""
    watch = watching or "status"
    bits = [f"{interval:g}s"]
    if graph:
        bits.append("graph")
    if refresh_slow:
        bits.append("refresh slow")
    lines = [
        c("  " + "─" * min(52, max(36, term_width() - 4)), _DIM, color=color),
        c(f"  watching  {watch}", _BOLD, _WHITE, color=color)
        + c("  ·  " + "  ·  ".join(bits), _DIM, color=color),
    ]
    if draft:
        lines.append(
            c("  › ", _BOLD, _RED, color=color)
            + c(draft, _WHITE, color=color)
            + c("█", _DIM, color=color)
        )
    if flash:
        for i, part in enumerate(flash.split("\n")):
            lines.insert(1 + i, c(f"  {part}", _BOLD, _YEL if i == 0 else _DIM, color=color))
    tw = term_width()
    return "\n".join(_fit_line(ln, tw) for ln in lines)


def enter_alt_screen() -> None:
    sys.stdout.write("\033[?1049h\033[H\033[J\033[?25l")
    sys.stdout.flush()


def leave_alt_screen() -> None:
    sys.stdout.write("\033[?25h\033[?1049l")
    sys.stdout.flush()


def _write_row(row: int, line: str) -> None:
    """Move to a 1-based row and replace that line only."""
    sys.stdout.write(f"\033[{max(1, row)};1H")
    sys.stdout.write(line)
    sys.stdout.write("\033[K")


def paint_frame(text: str) -> None:
    """Home, write each line in place, erase leftover rows. No full-screen wipe."""
    sys.stdout.write("\033[H")
    lines = text.splitlines() or [""]
    for i, line in enumerate(lines):
        if i:
            sys.stdout.write("\n")
        sys.stdout.write(line)
        sys.stdout.write("\033[K")
    sys.stdout.write("\033[J")
    sys.stdout.flush()


def paint_board_region(text: str, stop_row: int) -> None:
    """Rewrite rows 1..stop_row-1. Does not move the footer."""
    stop_row = max(2, stop_row)
    lines = text.splitlines() if text else []
    last = 0
    for i, line in enumerate(lines):
        row = 1 + i
        if row >= stop_row:
            break
        _write_row(row, line)
        last = row
    for row in range(last + 1, stop_row):
        _write_row(row, "")
    sys.stdout.flush()


def paint_chrome_region(row: int, text: str) -> None:
    """Rewrite the footer from *row* and clear anything below it."""
    lines = text.splitlines() or [""]
    for i, line in enumerate(lines):
        _write_row(row + i, line)
    sys.stdout.write("\033[J")
    sys.stdout.flush()


def paint_from_row(row: int, text: str) -> None:
    """Rewrite from a 1-based row to the end of the screen (prompt-only updates)."""
    paint_chrome_region(row, text)


def paint_region(row: int, text: str, *, clear_through: int | None = None) -> None:
    """Paint *text* at *row* without touching lines below *clear_through*."""
    lines = text.splitlines() or [""]
    end_row = row + len(lines) - 1
    for i, line in enumerate(lines):
        _write_row(row + i, line)
    if clear_through is not None and clear_through > end_row:
        for r in range(end_row + 1, clear_through + 1):
            _write_row(r, "")
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
