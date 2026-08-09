"""
Sliceable resources shared by the HTTP API and the CLI.

Users remember short names (gpu, cpu, temps). Combinations like
``gpu temp`` select a resource + field filters — no one-route-per-phrase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.collectors import get_inventory, get_vitals

# Canonical resource → display name
CANONICAL = (
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
    "scan",
    "all",
)

# What people type → canonical name
ALIASES: dict[str, str] = {
    "status": "status",
    "summary": "status",
    "cpu": "cpu",
    "processor": "cpu",
    "gpu": "gpu",
    "graphics": "gpu",
    "nvidia": "gpu",
    "vram": "gpu",
    "ram": "memory",
    "memory": "memory",
    "mem": "memory",
    "temp": "temps",
    "temps": "temps",
    "temperature": "temps",
    "temperatures": "temps",
    "thermal": "temps",
    "board": "board",
    "motherboard": "board",
    "mb": "board",
    "mobo": "board",
    "mainboard": "board",
    "os": "os",
    "system": "os",
    "host": "os",
    "kernel": "os",
    "disk": "disk",
    "storage": "disk",
    "ssd": "disk",
    "hdd": "disk",
    "drive": "disk",
    "net": "net",
    "network": "net",
    "wifi": "net",
    "eth": "net",
    "battery": "battery",
    "bat": "battery",
    "power": "battery",
    "scan": "scan",
    "inventory": "scan",
    "hw": "scan",
    "hardware": "scan",
    "all": "all",
    "everything": "all",
    "full": "all",
}

# Optional field tokens (not resources by themselves when mixed with a resource)
FIELD_ALIASES: dict[str, str] = {
    "temp": "temp",
    "temps": "temp",
    "temperature": "temp",
    "usage": "usage",
    "util": "usage",
    "load": "usage",
    "name": "name",
    "model": "name",
    "summary": "summary",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(resource: str, data: Any, **extra: Any) -> dict:
    out = {"ok": True, "at": _now(), "resource": resource, "data": data}
    out.update(extra)
    return out


def resolve_token(token: str) -> tuple[str | None, str | None]:
    """Return (resource|None, field|None) for one word."""
    t = token.strip().lower()
    if not t:
        return None, None
    if t in FIELD_ALIASES:
        return None, FIELD_ALIASES[t]
    if t in ALIASES:
        return ALIASES[t], None
    return None, None


def parse_query(tokens: list[str]) -> tuple[list[str], set[str], list[str]]:
    """
    Parse freeform tokens into (resources, fields, unknown).

    Examples:
      ['gpu'] → resources=['gpu'], fields={}
      ['gpu', 'temp'] → ['gpu'], {'temp'}
      ['cpu', 'gpu', 'temp'] → ['cpu','gpu'], {'temp'}
      ['temp'] → ['temps'], {}
    """
    resources: list[str] = []
    fields: set[str] = set()
    unknown: list[str] = []
    seen: set[str] = set()

    for raw in tokens:
        res, field = resolve_token(raw)
        if field:
            fields.add(field)
            continue
        if res:
            if res not in seen:
                resources.append(res)
                seen.add(res)
            continue
        unknown.append(raw)

    # Bare "temp" with no other resources → temps resource
    if not resources and "temp" in fields:
        resources = ["temps"]
        fields.discard("temp")

    # "temp" alone already handled; if only "usage" with nothing → status
    if not resources and fields:
        resources = ["status"]

    return resources, fields, unknown


# ---------- resource builders ----------


def resource_status() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    s = inv.get("summary") or {}
    cpu = vit.get("cpu") or {}
    gpus = vit.get("gpus") or []
    ram = (vit.get("memory") or {}).get("ram") or {}
    g0 = gpus[0] if gpus else {}
    return _ok(
        "status",
        {
            "hostname": s.get("hostname"),
            "os": s.get("os"),
            "cpu": s.get("cpu"),
            "gpus": s.get("gpus"),
            "ram_gb": s.get("ram_gb"),
            "uptime_seconds": s.get("uptime_seconds"),
            "live": {
                "cpu_percent": cpu.get("usage_percent"),
                "cpu_temp_c": _cpu_temp(cpu),
                "gpu_percent": g0.get("usage_percent"),
                "gpu_temp_c": g0.get("temperature_c"),
                "ram_percent": ram.get("percent"),
            },
        },
    )


def resource_cpu() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    cpu_inv = next((c for c in inv.get("components", []) if c.get("category") == "cpu"), {})
    cpu = vit.get("cpu") or {}
    return _ok(
        "cpu",
        {
            "name": cpu_inv.get("name") or cpu_inv.get("brand"),
            "cores_physical": cpu_inv.get("cores_physical"),
            "cores_logical": cpu_inv.get("cores_logical"),
            "freq_current_mhz": cpu.get("freq_current_mhz"),
            "freq_max_mhz": cpu_inv.get("freq_max_mhz"),
            "usage_percent": cpu.get("usage_percent"),
            "usage_per_core": cpu.get("usage_per_core"),
            "load_1m": cpu.get("load_1m"),
            "temp_c": _cpu_temp(cpu),
            "temperatures": cpu.get("temperatures"),
        },
    )


def resource_gpu() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    inv_gpus = [c for c in inv.get("components", []) if c.get("category") == "gpu"]
    live = vit.get("gpus") or []
    devices = []
    for i, g in enumerate(inv_gpus):
        live_g = live[i] if i < len(live) else (live[0] if live and i == 0 else {})
        # Match by name vaguely if indices differ
        if not live_g and live:
            for lg in live:
                if (lg.get("name") or "") in (g.get("name") or "") or (g.get("name") or "") in (
                    lg.get("name") or ""
                ):
                    live_g = lg
                    break
        devices.append(
            {
                "name": g.get("name") or live_g.get("name"),
                "vendor": g.get("vendor") or live_g.get("vendor"),
                "driver_version": g.get("driver_version"),
                "vram_total_mb": g.get("vram_total_mb") or live_g.get("vram_total_mb"),
                "vram_used_mb": live_g.get("vram_used_mb"),
                "usage_percent": live_g.get("usage_percent"),
                "temp_c": live_g.get("temperature_c"),
                "power_watts": live_g.get("power_watts"),
                "power_limit_watts": live_g.get("power_limit_watts"),
                "graphics_mhz": live_g.get("graphics_mhz"),
                "mem_mhz": live_g.get("mem_mhz"),
                "pci_id": g.get("pci_id"),
                "source": g.get("source") or live_g.get("source"),
            }
        )
    if not devices and live:
        for lg in live:
            devices.append(
                {
                    "name": lg.get("name"),
                    "vendor": lg.get("vendor"),
                    "vram_total_mb": lg.get("vram_total_mb"),
                    "vram_used_mb": lg.get("vram_used_mb"),
                    "usage_percent": lg.get("usage_percent"),
                    "temp_c": lg.get("temperature_c"),
                    "power_watts": lg.get("power_watts"),
                    "source": lg.get("source"),
                }
            )
    return _ok("gpu", {"count": len(devices), "devices": devices})


def resource_memory() -> dict:
    vit = get_vitals()
    mem = vit.get("memory") or {}
    return _ok("memory", mem)


def resource_temps() -> dict:
    vit = get_vitals()
    cpu = vit.get("cpu") or {}
    gpus = vit.get("gpus") or []
    return _ok(
        "temps",
        {
            "cpu_c": _cpu_temp(cpu),
            "cpu_sensors": cpu.get("temperatures"),
            "gpus": [{"name": g.get("name"), "temp_c": g.get("temperature_c")} for g in gpus],
            "all_sensors": vit.get("temperatures"),
        },
    )


def resource_board() -> dict:
    inv = get_inventory(include_pci=False)
    items = [
        c
        for c in inv.get("components", [])
        if c.get("category") in ("motherboard", "system", "bios", "chassis")
    ]
    by_cat = {c.get("category"): c for c in items}
    return _ok(
        "board",
        {
            "system": by_cat.get("system"),
            "motherboard": by_cat.get("motherboard"),
            "bios": by_cat.get("bios"),
            "chassis": by_cat.get("chassis"),
        },
    )


def resource_os() -> dict:
    inv = get_inventory(include_pci=False)
    for c in inv.get("components", []):
        if c.get("category") == "os":
            return _ok("os", c)
    return _ok("os", inv.get("summary") or {})


def resource_disk() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    disks = [c for c in inv.get("components", []) if c.get("category") == "disk"]
    parts = [c for c in inv.get("components", []) if c.get("category") == "partition"]
    storage = vit.get("storage") or {}
    rates = vit.get("rates") or {}
    return _ok(
        "disk",
        {
            "disks": disks,
            "partitions": parts or storage.get("partitions"),
            "rates_mbs": {
                "read": rates.get("disk_read_mbs"),
                "write": rates.get("disk_write_mbs"),
            },
            "io": storage.get("io"),
        },
    )


def resource_net() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    nets = [
        c
        for c in inv.get("components", [])
        if c.get("category") in ("network", "network_controller")
    ]
    rates = vit.get("rates") or {}
    return _ok(
        "net",
        {
            "interfaces": nets,
            "rates_mbs": {
                "recv": rates.get("net_recv_mbs"),
                "sent": rates.get("net_sent_mbs"),
            },
            "totals": (vit.get("network") or {}).get("total"),
        },
    )


def resource_battery() -> dict:
    vit = get_vitals()
    bat = vit.get("battery")
    if not bat:
        return _ok("battery", {"present": False, "note": "No battery detected (desktop or sensor missing)."})
    return _ok("battery", {"present": True, **bat})


def resource_scan(include_pci: bool = False) -> dict:
    inv = get_inventory(include_pci=include_pci)
    return _ok(
        "scan",
        {
            "summary": inv.get("summary"),
            "counts": inv.get("counts"),
            "components": inv.get("components"),
        },
        include_pci=include_pci,
    )


def resource_all() -> dict:
    return _ok(
        "all",
        {
            "status": resource_status()["data"],
            "cpu": resource_cpu()["data"],
            "gpu": resource_gpu()["data"],
            "memory": resource_memory()["data"],
            "temps": resource_temps()["data"],
            "board": resource_board()["data"],
            "os": resource_os()["data"],
            "disk": resource_disk()["data"],
            "net": resource_net()["data"],
            "battery": resource_battery()["data"],
        },
    )


HANDLERS: dict[str, Callable[..., dict]] = {
    "status": resource_status,
    "cpu": resource_cpu,
    "gpu": resource_gpu,
    "memory": resource_memory,
    "temps": resource_temps,
    "board": resource_board,
    "os": resource_os,
    "disk": resource_disk,
    "net": resource_net,
    "battery": resource_battery,
    "scan": resource_scan,
    "all": resource_all,
}


def get_resource(name: str, **kwargs: Any) -> dict:
    key = ALIASES.get(name.lower(), name.lower())
    handler = HANDLERS.get(key)
    if not handler:
        return {
            "ok": False,
            "at": _now(),
            "resource": name,
            "error": f"Unknown resource '{name}'. Try: {', '.join(CANONICAL)}",
        }
    if key == "scan":
        return handler(include_pci=bool(kwargs.get("include_pci", False)))
    return handler()


def apply_fields(payload: dict, fields: set[str]) -> dict:
    """Narrow a resource payload by field filters (temp, usage, name, summary)."""
    if not payload.get("ok") or not fields:
        return payload
    resource = payload.get("resource")
    data = payload.get("data")
    if data is None:
        return payload

    filtered: Any = data

    if "temp" in fields:
        filtered = _filter_temp(resource, data)
    if "usage" in fields:
        filtered = _filter_usage(resource, filtered if "temp" not in fields else data)
        if "temp" in fields:
            # merge both views
            t = _filter_temp(resource, data)
            u = _filter_usage(resource, data)
            filtered = {"temp": t, "usage": u}
    if "name" in fields and "temp" not in fields and "usage" not in fields:
        filtered = _filter_name(resource, data)
    if "summary" in fields and len(fields) == 1:
        filtered = _filter_summary(resource, data)

    out = dict(payload)
    out["data"] = filtered
    out["fields"] = sorted(fields)
    return out


def _filter_temp(resource: str | None, data: Any) -> Any:
    if resource == "cpu":
        return {"temp_c": data.get("temp_c"), "temperatures": data.get("temperatures")}
    if resource == "gpu":
        devices = data.get("devices") or []
        return {
            "devices": [{"name": d.get("name"), "temp_c": d.get("temp_c")} for d in devices],
        }
    if resource == "temps":
        return data
    if resource == "status":
        live = data.get("live") or {}
        return {
            "cpu_temp_c": live.get("cpu_temp_c"),
            "gpu_temp_c": live.get("gpu_temp_c"),
        }
    if resource == "all":
        return {
            "cpu": (data.get("cpu") or {}).get("temp_c"),
            "gpus": [
                {"name": d.get("name"), "temp_c": d.get("temp_c")}
                for d in ((data.get("gpu") or {}).get("devices") or [])
            ],
        }
    return {"note": f"No temp fields for '{resource}'", "raw": data}


def _filter_usage(resource: str | None, data: Any) -> Any:
    if resource == "cpu":
        return {
            "usage_percent": data.get("usage_percent"),
            "usage_per_core": data.get("usage_per_core"),
            "load_1m": data.get("load_1m"),
        }
    if resource == "gpu":
        return {
            "devices": [
                {
                    "name": d.get("name"),
                    "usage_percent": d.get("usage_percent"),
                    "vram_used_mb": d.get("vram_used_mb"),
                    "vram_total_mb": d.get("vram_total_mb"),
                }
                for d in (data.get("devices") or [])
            ]
        }
    if resource == "memory":
        ram = data.get("ram") or data
        return {
            "percent": ram.get("percent"),
            "used_gb": ram.get("used_gb"),
            "total_gb": ram.get("total_gb"),
        }
    if resource == "status":
        return data.get("live") or data
    return {"note": f"No usage fields for '{resource}'", "raw": data}


def _filter_name(resource: str | None, data: Any) -> Any:
    if resource == "cpu":
        return {"name": data.get("name")}
    if resource == "gpu":
        return {"names": [d.get("name") for d in (data.get("devices") or [])]}
    if resource == "board":
        mb = data.get("motherboard") or {}
        sys_ = data.get("system") or {}
        return {
            "system": sys_.get("name"),
            "motherboard": mb.get("name"),
        }
    if resource == "os":
        return {"name": data.get("name") or data.get("pretty_name")}
    if isinstance(data, dict) and "name" in data:
        return {"name": data.get("name")}
    return data


def _filter_summary(resource: str | None, data: Any) -> Any:
    if resource == "scan":
        return {"summary": data.get("summary"), "counts": data.get("counts")}
    if resource == "status":
        return data
    return data


def run_query(tokens: list[str], **kwargs: Any) -> dict:
    """
    Execute freeform tokens. Returns single resource payload or multi bundle.
    """
    resources, fields, unknown = parse_query(tokens)
    if unknown and not resources:
        return {
            "ok": False,
            "at": _now(),
            "error": f"Unknown: {', '.join(unknown)}",
            "hint": f"Try: {', '.join(CANONICAL)}",
            "aliases": sorted(set(ALIASES.keys())),
        }
    if not resources:
        return {
            "ok": False,
            "at": _now(),
            "error": "No resource specified",
            "hint": "Examples: gpu · cpu temp · temps · motherboard · status",
        }

    results = []
    for r in resources:
        payload = get_resource(r, **kwargs)
        payload = apply_fields(payload, fields)
        if unknown:
            payload["unknown_tokens"] = unknown
        results.append(payload)

    if len(results) == 1:
        return results[0]
    return {
        "ok": all(r.get("ok") for r in results),
        "at": _now(),
        "resource": "bundle",
        "query": tokens,
        "fields": sorted(fields),
        "results": results,
    }


def _cpu_temp(cpu: dict) -> float | None:
    temps = cpu.get("temperatures") or []
    if temps and temps[0].get("celsius") is not None:
        return temps[0]["celsius"]
    return None


# ---------- human text formatter ----------


def format_human(payload: dict) -> str:
    if not payload.get("ok"):
        err = payload.get("error") or "error"
        hint = payload.get("hint")
        lines = [f"Error: {err}"]
        if hint:
            lines.append(f"Hint: {hint}")
        return "\n".join(lines)

    if payload.get("resource") == "bundle":
        parts = [format_human(r) for r in payload.get("results") or []]
        return "\n\n".join(parts)

    r = payload.get("resource")
    d = payload.get("data")
    fields = set(payload.get("fields") or [])

    if r == "status":
        live = d.get("live") or {}
        lines = [
            f"{d.get('hostname') or 'host'}  ·  {d.get('os') or '—'}",
            f"CPU  {d.get('cpu') or '—'}",
            f"GPU  {', '.join(d.get('gpus') or []) or '—'}",
            f"RAM  {d.get('ram_gb')} GB",
            f"Live  CPU { _pct(live.get('cpu_percent')) }  ·  "
            f"GPU { _pct(live.get('gpu_percent')) }  ·  "
            f"RAM { _pct(live.get('ram_percent')) }",
            f"Temps  CPU {_deg(live.get('cpu_temp_c')) }  ·  GPU {_deg(live.get('gpu_temp_c')) }",
        ]
        return "\n".join(lines)

    if r == "cpu":
        if fields == {"temp"} or (fields & {"temp"} and "usage" not in fields and "name" not in fields):
            return f"CPU temp  {_deg(d.get('temp_c'))}"
        if fields == {"name"}:
            return f"CPU  {d.get('name') or '—'}"
        if fields == {"usage"}:
            return f"CPU load  {_pct(d.get('usage_percent'))}  ·  load1 {d.get('load_1m')}"
        return (
            f"CPU  {d.get('name') or '—'}\n"
            f"  Load   {_pct(d.get('usage_percent'))}\n"
            f"  Cores  {d.get('cores_physical')}c / {d.get('cores_logical')}t\n"
            f"  Freq   {d.get('freq_current_mhz') or '—'} MHz  (max {d.get('freq_max_mhz') or '—'})\n"
            f"  Temp   {_deg(d.get('temp_c'))}\n"
            f"  Load1  {d.get('load_1m')}"
        )

    if r == "gpu":
        devices = d.get("devices") or []
        if not devices:
            return "GPU  (none detected)"
        if "temp" in fields and "usage" not in fields and "name" not in fields:
            lines = ["GPU temps"]
            for g in devices:
                lines.append(f"  {g.get('name') or 'GPU'}  {_deg(g.get('temp_c'))}")
            return "\n".join(lines)
        if fields == {"name"}:
            return "GPU\n" + "\n".join(f"  {g.get('name')}" for g in devices)
        if fields == {"usage"}:
            lines = ["GPU load"]
            for g in devices:
                lines.append(
                    f"  {g.get('name') or 'GPU'}  {_pct(g.get('usage_percent'))}  ·  "
                    f"VRAM {g.get('vram_used_mb') or '—'} / {g.get('vram_total_mb') or '—'} MB"
                )
            return "\n".join(lines)
        lines = ["GPU"]
        for g in devices:
            lines.append(f"  {g.get('name') or '—'}")
            lines.append(
                f"    Load {_pct(g.get('usage_percent'))}  ·  Temp {_deg(g.get('temp_c'))}  ·  "
                f"Power {g.get('power_watts') if g.get('power_watts') is not None else '—'} W"
            )
            lines.append(
                f"    VRAM {g.get('vram_used_mb') or '—'} / {g.get('vram_total_mb') or '—'} MB  ·  "
                f"Driver {g.get('driver_version') or '—'}"
            )
        return "\n".join(lines)

    if r == "memory":
        ram = d.get("ram") or d
        swap = d.get("swap") or {}
        return (
            f"Memory  {_pct(ram.get('percent'))}  ·  "
            f"{ram.get('used_gb')} / {ram.get('total_gb')} GB\n"
            f"  Available  {ram.get('available_gb')} GB\n"
            f"  Swap       {_pct(swap.get('percent'))}  ·  "
            f"{swap.get('used_gb')} / {swap.get('total_gb')} GB"
        )

    if r == "temps":
        lines = [
            f"Temps  CPU {_deg(d.get('cpu_c'))}",
        ]
        for g in d.get("gpus") or []:
            lines.append(f"       GPU {g.get('name') or ''}  {_deg(g.get('temp_c'))}".rstrip())
        return "\n".join(lines)

    if r == "board":
        sys_ = d.get("system") or {}
        mb = d.get("motherboard") or {}
        bios = d.get("bios") or {}
        return (
            f"Machine       {sys_.get('name') or '—'}\n"
            f"Motherboard   {mb.get('name') or '—'}\n"
            f"BIOS          {bios.get('name') or bios.get('version') or '—'}"
        )

    if r == "os":
        return (
            f"OS       {d.get('name') or d.get('pretty_name') or '—'}\n"
            f"Kernel   {d.get('kernel') or d.get('release') or '—'}\n"
            f"Host     {d.get('hostname') or '—'}\n"
            f"Desktop  {d.get('desktop_environment') or '—'}  ·  "
            f"{d.get('session_type') or '—'}\n"
            f"Arch     {d.get('architecture') or '—'}"
        )

    if r == "disk":
        lines = ["Disk"]
        for disk in d.get("disks") or []:
            lines.append(
                f"  {disk.get('name') or disk.get('device')}  "
                f"{disk.get('size_gb')} GB  {disk.get('media') or ''}".rstrip()
            )
        for p in (d.get("partitions") or [])[:8]:
            lines.append(
                f"  {p.get('mountpoint') or p.get('device')}  "
                f"{p.get('percent')}%  ·  {p.get('used_gb')}/{p.get('total_gb')} GB"
            )
        rates = d.get("rates_mbs") or {}
        if rates:
            lines.append(f"  I/O  read {rates.get('read')}  write {rates.get('write')} MB/s")
        return "\n".join(lines)

    if r == "net":
        rates = d.get("rates_mbs") or {}
        lines = [
            f"Network  ↓ {rates.get('recv')}  ↑ {rates.get('sent')} MB/s",
        ]
        for iface in d.get("interfaces") or []:
            if iface.get("category") == "network_controller":
                lines.append(f"  chip  {iface.get('name')}")
            else:
                up = iface.get("is_up")
                flag = "up" if up else "down" if up is False else "?"
                lines.append(f"  {iface.get('name')}  {flag}")
        return "\n".join(lines)

    if r == "battery":
        if not d.get("present"):
            return "Battery  not present / not reported"
        plug = "AC" if d.get("power_plugged") else "battery"
        return f"Battery  {d.get('percent')}%  ·  {plug}"

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
        return "\n".join(lines)

    if r == "all":
        # compact dump of nested
        import json as _json

        return _json.dumps(d, indent=2)

    import json as _json

    return _json.dumps(payload, indent=2)


def _pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{round(float(v))}%"
    except (TypeError, ValueError):
        return "—"


def _deg(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{round(float(v))}°C"
    except (TypeError, ValueError):
        return "—"


def list_commands_help() -> str:
    return """
sysinspect — System Inspector CLI
=================================
Also installable as:  si

USAGE
  sysinspect <resource> [resource…] [field…] [options]
  sysinspect watch|graph|live <resource> [field…] [--interval 1]
  sysinspect help

RESOURCES (short names you type)
  status, summary          Quick host + live overview
  cpu, processor           CPU model, load, freq, temp
  gpu, graphics, nvidia    GPU(s): load, VRAM, temp, power
  ram, memory, mem         Memory / swap
  temp, temps, thermal     CPU + GPU temperatures
  board, motherboard, mb   System / motherboard / BIOS
  os, system, host         OS, kernel, desktop
  disk, storage, ssd       Disks, partitions, I/O rates
  net, network, wifi       Interfaces + throughput
  battery, bat             Laptop battery if present
  scan, inventory, hw      Hardware inventory summary
  all, everything          Big combined snapshot

FIELDS (optional, combine with a resource)
  temp, temperature        Only temperatures
  usage, util, load        Only utilization
  name, model              Only names/models
  summary                  Short scan-style summary

EXAMPLES
  sysinspect gpu
  sysinspect cpu temp
  sysinspect status
  sysinspect watch gpu
  sysinspect graph temps
  sysinspect live cpu temp --interval 0.5
  sysinspect ram --json

OPTIONS
  --json, -j          Machine-readable JSON
  --plain, -p         No banner / colors / meters (scripts)
  --pci               Include full PCI list (scan only)
  --interval N        Seconds between watch updates (default 1)
  --no-graph          Watch text only (skip live ASCII graph)

API (when UI/server is running on :8787)
  GET /api/status | /api/cpu | /api/gpu | /api/memory | /api/temps
  GET /api/board | /api/os | /api/disk | /api/net | /api/battery
  GET /api/scan | /api/all | /api/query?q=gpu+temp
  GET /api/help
""".strip()

