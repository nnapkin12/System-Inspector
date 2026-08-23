"""Plain-text CLI output."""

from __future__ import annotations

import json
from typing import Any

from backend.collectors.gpu import short_gpu_name as short_gpu
from backend.fields import NET_DETAIL_FIELDS, OS_DETAIL_FIELDS

# Sort connections/listeners: worst health first
_HEALTH_SORT = {"bad": 0, "warn": 1, "good": 2, "unknown": 3}

_CPU_TEMP_MARKERS = ("k10temp", "coretemp", "cpu", "tctl", "tdie", "package id")
_GPU_TEMP_MARKERS = ("nv_temp", "nvidia", "amdgpu", "radeon", "nouveau")


def _is_cpu_or_gpu_temp_label(label: str, gpu_names: set[str]) -> bool:
    low = (label or "").lower()
    if any(m in low for m in _CPU_TEMP_MARKERS):
        return True
    if any(m in low for m in _GPU_TEMP_MARKERS):
        return True
    return any(name and name in low for name in gpu_names)


def pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{round(float(v))}%"
    except (TypeError, ValueError):
        return "—"


def deg(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{round(float(v))}°C"
    except (TypeError, ValueError):
        return "—"


def fmt_uptime(secs: Any) -> str:
    if secs is None:
        return "—"
    try:
        s = int(float(secs))
    except (TypeError, ValueError):
        return "—"
    if s < 0:
        s = 0
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours or days:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    parts.append(f"{mins} min{'s' if mins != 1 else ''}")
    return ", ".join(parts)


def format_human(payload: dict, *, color: bool = False, verbose: bool = False) -> str:
    if not payload.get("ok"):
        err = payload.get("error") or "error"
        hint = payload.get("hint")
        lines = [f"Error: {err}"]
        if hint:
            lines.append(f"Hint: {hint}")
        if color:
            from backend.tui import paint_health

            lines[0] = paint_health(lines[0], "bad", color=color)
        return "\n".join(lines)

    if payload.get("resource") == "bundle":
        v = verbose or payload.get("verbose", False)
        parts = [format_human(r, color=color, verbose=v) for r in payload.get("results") or []]
        return "\n\n".join(parts)

    r = payload.get("resource")
    d = payload.get("data")
    fields = set(payload.get("fields") or [])
    verbose = verbose or payload.get("verbose", False)

    if r == "status":
        live = d.get("live") or {}
        gpus = d.get("gpus") or []
        gpus_s = ", ".join(short_gpu(g) for g in gpus) if gpus else "—"
        live_bits = [
            f"CPU {pct(live.get('cpu_percent'))}",
        ]
        if live.get("gpu_percent") is not None:
            live_bits.append(f"GPU {pct(live.get('gpu_percent'))}")
        live_bits.append(f"RAM {pct(live.get('ram_percent'))}")
        lines = [
            f"CPU  {d.get('cpu') or '—'}",
            f"GPU  {gpus_s}",
            f"RAM  {d.get('ram_gb')} GB",
            "Live  " + "  ·  ".join(live_bits),
            f"Temps  CPU {deg(live.get('cpu_temp_c'))}  ·  GPU {deg(live.get('gpu_temp_c'))}",
            f"Uptime  {fmt_uptime(d.get('uptime_seconds'))}",
        ]
        vram_u, vram_t = live.get("gpu_vram_used_mb"), live.get("gpu_vram_total_mb")
        gpu_more = []
        if vram_u is not None and vram_t is not None:
            gpu_more.append(f"VRAM {round(float(vram_u) / 1024, 1)}/{round(float(vram_t) / 1024, 1)} GB")
        if live.get("gpu_power_w") is not None:
            gpu_more.append(f"{live.get('gpu_power_w')} W")
        if live.get("gpu_clock_mhz") is not None:
            gpu_more.append(f"{int(round(float(live['gpu_clock_mhz'])))} MHz")
        if gpu_more:
            lines.append("GPU   " + "  ·  ".join(gpu_more))
        if live.get("rates_ready") and live.get("net_recv_mbs") is not None:
            lines.append(
                f"Net   ↓{live.get('net_recv_mbs')} ↑{live.get('net_sent_mbs')} MB/s"
            )
        if live.get("battery_percent") is not None:
            plug = "AC" if live.get("battery_plugged") else "battery"
            lines.append(f"Battery  {pct(live.get('battery_percent'))}  ·  {plug}")
        if live.get("gpu_percent") is None and live.get("gpu_note"):
            lines.append(f"GPU   {live.get('gpu_note')}")
        return "\n".join(lines)

    if r == "cpu":
        if fields == {"temp"} or (fields & {"temp"} and "usage" not in fields and "name" not in fields):
            return f"CPU temp  {deg(d.get('temp_c'))}"
        if fields == {"name"}:
            return f"CPU  {d.get('name') or '—'}"
        if fields == {"usage"}:
            return f"CPU load  {pct(d.get('usage_percent'))}  ·  load1 {d.get('load_1m')}"
        per = d.get("usage_per_core") or []
        per_s = ""
        if per:
            bits = "  ".join(pct(x) for x in per)
            per_s = f"\n  Each   {bits}"
        return (
            f"CPU  {d.get('name') or '—'}\n"
            f"  Load   {pct(d.get('usage_percent'))}\n"
            f"  Cores  {d.get('cores_physical')}c / {d.get('cores_logical')}t\n"
            f"  Freq   {d.get('freq_current_mhz') or '—'} MHz  (max {d.get('freq_max_mhz') or '—'})\n"
            f"  Temp   {deg(d.get('temp_c'))}\n"
            f"  Load1  {d.get('load_1m')}"
            f"{per_s}"
        )

    if r == "gpu":
        devices = d.get("devices") or []
        if not devices:
            return "GPU  (none detected)"
        if "temp" in fields and "usage" not in fields and "name" not in fields:
            lines = ["GPU temps"]
            for g in devices:
                line = f"  {short_gpu(g.get('name')):28}  {deg(g.get('temp_c'))}"
                if g.get("temp_c") is None and g.get("note"):
                    line = f"  {short_gpu(g.get('name')):28}  {g.get('note')}"
                lines.append(line)
            return "\n".join(lines)
        if fields == {"name"}:
            return "GPU\n" + "\n".join(f"  {short_gpu(g.get('name'))}" for g in devices)
        if fields == {"usage"}:
            lines = ["GPU load"]
            for g in devices:
                if g.get("usage_percent") is None and g.get("note"):
                    lines.append(
                        f"  {short_gpu(g.get('name')):28}  {g.get('note')}"
                    )
                else:
                    lines.append(
                        f"  {short_gpu(g.get('name')):28}  {pct(g.get('usage_percent'))}  ·  "
                        f"VRAM {g.get('vram_used_mb') or '—'} / {g.get('vram_total_mb') or '—'} MB"
                    )
            return "\n".join(lines)
        lines = ["GPU"]
        for g in devices:
            name = short_gpu(g.get("name"))
            has_load = g.get("usage_percent") is not None or g.get("vram_total_mb") is not None
            if not has_load:
                t = deg(g.get("temp_c"))
                if t != "—":
                    lines.append(f"  {name}  {t}")
                elif g.get("note"):
                    lines.append(f"  {name}  {g.get('note')}")
                else:
                    lines.append(f"  {name}")
                continue
            lines.append(f"  {name}")
            lines.append(
                f"    Load {pct(g.get('usage_percent'))}  ·  Temp {deg(g.get('temp_c'))}  ·  "
                f"Power {g.get('power_watts') if g.get('power_watts') is not None else '—'} W"
            )
            vram_u, vram_t = g.get("vram_used_mb"), g.get("vram_total_mb")
            freq = g.get("graphics_mhz")
            freq_s = f"{freq} MHz" if freq is not None else "—"
            lines.append(
                f"    VRAM {vram_u or '—'} / {vram_t or '—'} MB  ·  "
                f"Core {freq_s}  ·  Driver {g.get('driver_version') or '—'}"
            )
        return "\n".join(lines)

    if r == "memory":
        ram = d.get("ram") or d
        swap = d.get("swap") or {}
        return (
            f"Memory  {pct(ram.get('percent'))}  ·  "
            f"{ram.get('used_gb')} / {ram.get('total_gb')} GB\n"
            f"  Available  {ram.get('available_gb')} GB\n"
            f"  Swap       {pct(swap.get('percent'))}  ·  "
            f"{swap.get('used_gb')} / {swap.get('total_gb')} GB"
        )

    if r == "temps":
        lines = [f"CPU {deg(d.get('cpu_c'))}"]
        gpu_names: set[str] = set()
        for g in d.get("gpus") or []:
            name = short_gpu(g.get("name"))
            gpu_names.add((name or "").lower())
            if g.get("temp_c") is None and g.get("note"):
                lines.append(f"GPU {name}  {g.get('note')}")
            else:
                lines.append(f"GPU {name}  {deg(g.get('temp_c'))}")
        for s in d.get("all_sensors") or []:
            label = (s.get("label") or s.get("sensor") or "sensor").strip()
            if _is_cpu_or_gpu_temp_label(label, gpu_names):
                continue
            if s.get("celsius") is None:
                continue
            lines.append(f"{label}  {deg(s.get('celsius'))}")
        return "\n".join(lines)

    if r == "fans":
        fans = d.get("fans") or []
        if not fans:
            return "Fans  (none reported — laptop EC often hides RPM)"
        lines = ["Fans"]
        for f in fans:
            label = f.get("label") or f.get("sensor") or "fan"
            if f.get("rpm") is not None:
                lines.append(f"  {label:28}  {f.get('rpm')} RPM")
            elif f.get("percent") is not None:
                lines.append(f"  {label:28}  {pct(f.get('percent'))}")
            else:
                lines.append(f"  {label}")
        return "\n".join(lines)

    if r == "board":
        sys_ = d.get("system") or {}
        mb = d.get("motherboard") or {}
        bios = d.get("bios") or {}
        chassis = d.get("chassis") or {}
        lines = [
            f"Machine       {sys_.get('name') or '—'}",
            f"Motherboard   {mb.get('name') or '—'}",
            f"BIOS          {bios.get('name') or bios.get('version') or '—'}",
        ]
        if bios.get("date"):
            lines.append(f"BIOS date     {bios.get('date')}")
        if chassis.get("name") and chassis.get("name") != "Chassis":
            lines.append(f"Chassis       {chassis.get('name')}")
        return "\n".join(lines)

    if r == "os":
        # Filtered one-liners
        if fields & OS_DETAIL_FIELDS:
            lines = []
            if "version" in fields or "name" in fields:
                lines.append(f"OS       {d.get('pretty_name') or d.get('name') or '—'}")
            if "kernel" in fields:
                lines.append(f"Kernel   {d.get('kernel') or d.get('release') or '—'}")
            if "hostname" in fields:
                lines.append(f"Host     {d.get('hostname') or '—'}")
            if "desktop" in fields:
                lines.append(
                    f"Desktop  {d.get('desktop_environment') or '—'}  ·  "
                    f"{d.get('session_type') or '—'}"
                )
            if "arch" in fields:
                lines.append(f"Arch     {d.get('architecture') or d.get('machine') or '—'}")
            return "\n".join(lines) if lines else "—"
        from backend.tui import format_os_card

        return format_os_card(d, color=color)

    if r == "uptime":
        return f"Uptime   {d.get('human') or fmt_uptime(d.get('uptime_seconds'))}"

    if r == "version":
        from backend.tui import format_version_card

        return format_version_card(d, color=color)

    if r == "disk":
        lines = ["Disk"]
        for disk in d.get("disks") or []:
            lines.append(
                f"  {disk.get('name') or disk.get('device')}  "
                f"{disk.get('size_gb')} GB  {disk.get('media') or ''}".rstrip()
            )
        for p in d.get("partitions") or []:
            fs = p.get("fstype") or ""
            fs_s = f"  {fs}" if fs else ""
            lines.append(
                f"  {p.get('mountpoint') or p.get('device')}  "
                f"{p.get('percent')}%  ·  {p.get('used_gb')}/{p.get('total_gb')} GB{fs_s}"
            )
        rates = d.get("rates_mbs") or {}
        if rates:
            lines.append(f"  I/O  read {rates.get('read')}  write {rates.get('write')} MB/s")
        return "\n".join(lines)

    if r == "net":
        net_fields = fields & NET_DETAIL_FIELDS
        if net_fields == {"ip"}:
            lines: list[str] = []
            for row in d.get("addresses") or []:
                lines.append(
                    f"  {row.get('interface'):10}  {row.get('family') or 'ip':5}  "
                    f"{row.get('address')}  /{row.get('netmask') or '—'}"
                )
            return "\n".join(lines) if lines else "  (none)"

        if net_fields == {"gateway"}:
            gw = d.get("gateway") or {}
            iface = gw.get("interface") or "—"
            return f"  {gw.get('gateway') or '—'}  ·  {iface}"

        if net_fields == {"dns"}:
            dns = d.get("dns") or {}
            servers = dns.get("servers") or []
            if not servers:
                return f"  {dns.get('note') or '(none)'}"
            return "\n".join(f"  {s}" for s in servers)

        if net_fields == {"connections"}:
            from backend.tui import paint_health

            block = d.get("connections") or {}
            lines: list[str] = []
            if block.get("note"):
                lines.append(f"  {block.get('note')}")
            conns = list(block.get("connections") or [])
            if conns:
                n = block.get("total") or len(conns)
                word = "connection" if n == 1 else "connections"
                lines.append(f"  {n} {word}")
            conns = sorted(
                conns,
                key=lambda c: (
                    _HEALTH_SORT.get(c.get("health") or "unknown", 9),
                    c.get("process") or "",
                    c.get("remote") or "",
                ),
            )
            for conn in conns:
                proc = conn.get("process") or "?"
                pid = conn.get("pid")
                pid_s = f"pid {pid}" if pid else "pid —"
                health = conn.get("health") or "unknown"
                row = (
                    f"  {conn.get('type') or 'TCP':4}  {conn.get('local') or '—':22} → "
                    f"{conn.get('remote') or '—':22}  {conn.get('status') or '—':12}  "
                    f"{proc} ({pid_s})"
                )
                lines.append(paint_health(row, health, color=color))
            return "\n".join(lines) if lines else "  (none)"

        if net_fields == {"listen"}:
            from backend.tui import paint_health

            block = d.get("listeners") or {}
            lines: list[str] = []
            if block.get("note"):
                lines.append(f"  {block.get('note')}")
            listeners = sorted(
                block.get("listeners") or [],
                key=lambda r: (
                    _HEALTH_SORT.get(r.get("health") or "unknown", 9),
                    r.get("process") or "",
                    r.get("address") or "",
                ),
            )
            if listeners:
                n = block.get("total") or len(listeners)
                word = "listener" if n == 1 else "listeners"
                lines.append(f"  {n} {word}")
            for row in listeners:
                proc = row.get("process") or "?"
                pid = row.get("pid")
                pid_s = f"pid {pid}" if pid else "pid —"
                health = row.get("health") or "unknown"
                line = f"  {row.get('address') or '—':22}  {proc} ({pid_s})"
                lines.append(paint_health(line, health, color=color))
            return "\n".join(lines) if lines else "  (none)"

        if net_fields == {"routes"}:
            block = d.get("routes") or {}
            lines: list[str] = []
            for row in block.get("routes") or []:
                if row.get("route"):
                    lines.append(f"  {row.get('route')}")
                else:
                    lines.append(
                        f"  {row.get('destination')} via {row.get('gateway')} dev {row.get('interface')}"
                    )
            return "\n".join(lines) if lines else "  (none)"

        if net_fields == {"wifi"}:
            from backend.tui import paint_health

            block = d.get("wifi") or {}
            if not block.get("available"):
                return f"  {block.get('note') or '(not available)'}"
            active = block.get("active") or {}
            if active.get("ssid"):
                sig = active.get("signal")
                sig_s = f"{sig}%" if sig is not None else "—"
                sec = active.get("security") or "—"
                if sig is None:
                    wifi_health = "unknown"
                elif sig >= 70:
                    wifi_health = "good"
                elif sig >= 40:
                    wifi_health = "warn"
                else:
                    wifi_health = "bad"
                line = f"  {active.get('ssid')}  ·  {sig_s}  ·  {sec}"
                lines = [paint_health(line, wifi_health, color=color)]
            else:
                lines = [f"  {active.get('ssid') or '—'}"]
            nearby = [n for n in (block.get("networks") or []) if not n.get("active") and n.get("ssid")]
            if nearby:
                lines.append("  nearby")
                for n in nearby:
                    sig = n.get("signal")
                    sig_s = f"{sig}%" if sig is not None else "—"
                    sec = n.get("security") or "—"
                    lines.append(f"    {n.get('ssid')}  ·  {sig_s}  ·  {sec}")
            return "\n".join(lines)

        if net_fields == {"public"}:
            block = d.get("public") or {}
            if block.get("address"):
                return f"  {block.get('address')}"
            return f"  {block.get('note') or 'unavailable'}"

        rates = d.get("rates_mbs") or {}
        lines = [
            f"Network  ↓ {rates.get('recv')}  ↑ {rates.get('sent')} MB/s",
        ]
        gw = d.get("gateway") or {}
        if gw.get("gateway"):
            lines.append(f"  gateway  {gw.get('gateway')}  ·  iface {gw.get('interface') or '—'}")
        dns = d.get("dns") or {}
        if dns.get("servers"):
            lines.append(f"  DNS      {', '.join(dns.get('servers'))}")
        for row in d.get("addresses") or []:
            fam = row.get("family") or "ip"
            iface = (row.get("interface") or "—")[:10]
            lines.append(
                f"  {iface:10}  {fam:5}  {row.get('address')}  /{row.get('netmask') or '—'}"
            )
        return "\n".join(lines)

    if r == "battery":
        if not d.get("present"):
            return "Battery  not present / not reported"
        plug = "AC" if d.get("power_plugged") else "battery"
        level = d.get("percent")
        pct_s = f"{int(round(float(level)))}%" if level is not None else "—"
        left = d.get("secs_left")
        extra = f"  ·  {fmt_uptime(left)} left" if left else ""
        return f"Battery  {pct_s}  ·  {plug}{extra}"

    if r == "scan":
        s = d.get("summary") or {}
        counts = d.get("counts") or {}
        lines = [
            f"Scan  {s.get('hostname')}  ·  {s.get('os')}",
            f"  CPU   {s.get('cpu')}",
            f"  GPU   {', '.join(s.get('gpus') or [])}",
            f"  RAM   {s.get('ram_gb')} GB",
            f"  Items {counts.get('total_components')}",
        ]
        order = (
            "cpu",
            "gpu",
            "memory",
            "disk",
            "partition",
            "network",
            "network_controller",
            "motherboard",
            "system",
            "bios",
            "chassis",
            "os",
        )
        by_cat: dict[str, list[dict]] = {}
        for item in d.get("components") or []:
            cat = str(item.get("category") or "other")
            by_cat.setdefault(cat, []).append(item)
        for cat in order:
            items = by_cat.pop(cat, [])
            if not items:
                continue
            for item in items:
                name = item.get("name") or item.get("device") or item.get("mountpoint") or "—"
                lines.append(f"  {cat:12}  {name}")
        for cat in sorted(by_cat):
            for item in by_cat[cat]:
                name = item.get("name") or item.get("device") or "—"
                lines.append(f"  {cat:12}  {name}")
        return "\n".join(lines)

    if r == "all":
        parts: list[str] = []
        for name in (
            "status",
            "cpu",
            "gpu",
            "memory",
            "temps",
            "board",
            "os",
            "disk",
            "net",
            "battery",
            "fans",
            "uptime",
            "version",
        ):
            section = d.get(name)
            if section is None:
                continue
            if isinstance(section, dict) and section.get("ok") is False:
                parts.append(format_human(section, color=color, verbose=verbose))
                continue
            parts.append(
                format_human(
                    {"ok": True, "resource": name, "data": section},
                    color=color,
                    verbose=verbose,
                )
            )
        return "\n\n".join(parts) if parts else json.dumps(d, indent=2)

    return json.dumps(payload, indent=2)
