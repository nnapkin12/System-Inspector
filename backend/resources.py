"""
Sliceable resources shared by the HTTP API and the CLI.

Users remember short names (gpu, cpu, temps). Combinations like
``gpu temp`` select a resource + field filters — no one-route-per-phrase.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from backend.collectors import get_inventory, get_vitals
from backend.collectors.gpu import short_gpu_name as _short_gpu

# Canonical resource → display name
CANONICAL = (
    "status",
    "cpu",
    "gpu",
    "memory",
    "temps",
    "fans",
    "board",
    "os",
    "disk",
    "net",
    "battery",
    "scan",
    "uptime",
    "version",
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
    # note: "host" = full OS block; use "hostname" field for host name only
    "host": "os",
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
    "fans": "fans",
    "fan": "fans",
    "cooling": "fans",
    "scan": "scan",
    "inventory": "scan",
    "hw": "scan",
    "hardware": "scan",
    "uptime": "uptime",
    "up": "uptime",
    # bare "version" / "ver" → System Inspector app version (not OS)
    "version": "version",
    "ver": "version",
    "about": "version",
    "all": "all",
    "everything": "all",
    "full": "all",
}

# Optional field tokens (combine with a resource, or alone for a few shortcuts)
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
    # OS detail slices — "si kernel" or "si os kernel" → kernel line only
    "kernel": "kernel",
    "hostname": "hostname",
    "desktop": "desktop",
    "de": "desktop",
    "arch": "arch",
    "architecture": "arch",
    "distro": "version",  # OS pretty name (with os context)
    "release": "version",
}

# Fields that mean "zoom into OS" when typed alone (si kernel → OS kernel line)
_OS_DETAIL_FIELDS = frozenset({"kernel", "hostname", "desktop", "arch", "version", "name"})



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(resource: str, data: Any, **extra: Any) -> dict:
    out = {"ok": True, "at": _now(), "resource": resource, "data": data}
    out.update(extra)
    return out


def resolve_token(token: str) -> tuple[str | None, str | None]:
    """Return (resource|None, field|None) for one word (simple cases)."""
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

    Smart rules (so extra words actually narrow the answer):
      si kernel           → os + field kernel  (one line)
      si os version       → os + field version (Pop!_OS only, not full block)
      si version          → app version (System Inspector 0.x)
      si temp             → temps resource
    """
    raw_tokens = [t.strip() for t in tokens if t and t.strip()]
    lower = [t.lower() for t in raw_tokens]

    # Will "version" mean OS distro name, or this app's version?
    os_context = any(
        ALIASES.get(t) == "os" or t in ("os", "system") for t in lower
    )

    resources: list[str] = []
    fields: set[str] = set()
    unknown: list[str] = []
    seen: set[str] = set()

    for t in lower:
        # Dual meaning: "version"
        if t in ("version", "ver"):
            if os_context:
                fields.add("version")
            else:
                if "version" not in seen:
                    resources.append("version")
                    seen.add("version")
            continue

        res, field = resolve_token(t)
        if field:
            fields.add(field)
            continue
        if res:
            if res not in seen:
                resources.append(res)
                seen.add(res)
            continue
        unknown.append(t)

    # Bare temp → temps resource
    if not resources and "temp" in fields:
        resources = ["temps"]
        fields.discard("temp")

    # Bare kernel / hostname / desktop / … → OS slice
    if not resources and fields & _OS_DETAIL_FIELDS:
        resources = ["os"]

    # leftover bare fields (e.g. only "usage") → status overview
    if not resources and fields:
        resources = ["status"]

    return resources, fields, unknown


# ---------- resource builders ----------


def resource_status() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    s = inv.get("summary") or {}
    cpu = vit.get("cpu") or {}
    ram = (vit.get("memory") or {}).get("ram") or {}
    gpus = vit.get("gpus") or []
    # Prefer discrete NVIDIA for the summary "GPU" slots when multi-GPU
    g0 = next(
        (g for g in gpus if "nvidia" in (g.get("vendor") or "").lower() or "geforce" in (g.get("name") or "").lower()),
        None,
    )
    if g0 is None:
        g0 = gpus[0] if gpus else {}
    # secondary for a second temperature if available
    others = [g for g in gpus if g is not g0]
    g1 = others[0] if others else {}
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
                "gpu_temp_c": g0.get("temperature_c") if g0.get("temperature_c") is not None else g1.get("temperature_c"),
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
    live = list(vit.get("gpus") or [])
    used_live: set[int] = set()

    def _match_live(g: dict) -> dict:
        g_vendor = (g.get("vendor") or "").lower()
        g_name = (g.get("name") or "").lower()
        # 1) vendor + name token
        for i, lg in enumerate(live):
            if i in used_live:
                continue
            lv = (lg.get("vendor") or "").lower()
            ln = (lg.get("name") or "").lower()
            if g_vendor and lv:
                if g_vendor in lv or lv in g_vendor or (
                    "nvidia" in g_vendor and "nvidia" in (lv + ln)
                ) or (
                    "amd" in g_vendor and ("amd" in lv or "radeon" in lv or "amd" in ln)
                ) or (
                    "intel" in g_vendor and ("intel" in lv or "i915" in lv)
                ):
                    # Prefer NVIDIA live for NVIDIA inventory, etc.
                    if ("nvidia" in g_vendor and "nvidia" not in lv and "nvidia" not in ln
                            and "nv" not in ln):
                        continue
                    used_live.add(i)
                    return lg
        # 2) substring name match
        for i, lg in enumerate(live):
            if i in used_live:
                continue
            ln = (lg.get("name") or "").lower()
            if ln and (ln in g_name or g_name in ln or any(
                tok in ln for tok in re.findall(r"[a-z0-9]{4,}", g_name) if len(tok) > 4
            )):
                used_live.add(i)
                return lg
        return {}

    devices = []
    for g in inv_gpus:
        live_g = _match_live(g)
        short = _short_gpu(g.get("name") or live_g.get("name"))
        devices.append(
            {
                "name": short,
                "full_name": g.get("pci_name") or g.get("name") or live_g.get("name"),
                "vendor": g.get("vendor") or live_g.get("vendor"),
                "driver_version": g.get("driver_version") or live_g.get("driver_version"),
                "vram_total_mb": g.get("vram_total_mb") or live_g.get("vram_total_mb"),
                "vram_used_mb": live_g.get("vram_used_mb"),
                "usage_percent": live_g.get("usage_percent"),
                "temp_c": live_g.get("temperature_c"),
                "power_watts": live_g.get("power_watts"),
                "power_limit_watts": live_g.get("power_limit_watts"),
                "graphics_mhz": live_g.get("graphics_mhz"),
                "mem_mhz": live_g.get("mem_mhz"),
                "fan_percent": live_g.get("fan_percent"),
                "pci_id": g.get("pci_id"),
                "source": live_g.get("source") or g.get("source"),
            }
        )

    # Unmatched live sensors (e.g. dGPU when inventory missed NVML name)
    for i, lg in enumerate(live):
        if i in used_live:
            continue
        devices.append(
            {
                "name": _short_gpu(lg.get("name")),
                "full_name": lg.get("name"),
                "vendor": lg.get("vendor"),
                "vram_total_mb": lg.get("vram_total_mb"),
                "vram_used_mb": lg.get("vram_used_mb"),
                "usage_percent": lg.get("usage_percent"),
                "temp_c": lg.get("temperature_c"),
                "power_watts": lg.get("power_watts"),
                "power_limit_watts": lg.get("power_limit_watts"),
                "graphics_mhz": lg.get("graphics_mhz"),
                "mem_mhz": lg.get("mem_mhz"),
                "fan_percent": lg.get("fan_percent"),
                "source": lg.get("source"),
            }
        )
    if not devices and live:
        for lg in live:
            devices.append(
                {
                    "name": _short_gpu(lg.get("name")),
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
    # Prefer resource_gpu matching when inventory is available — still use short names here
    matched = resource_gpu()["data"].get("devices") or []
    gpu_temps = [
        {"name": g.get("name"), "temp_c": g.get("temp_c")}
        for g in matched
    ]
    if not gpu_temps:
        gpu_temps = [
            {"name": _short_gpu(g.get("name")), "temp_c": g.get("temperature_c")} for g in gpus
        ]
    return _ok(
        "temps",
        {
            "cpu_c": _cpu_temp(cpu),
            "cpu_sensors": cpu.get("temperatures"),
            "gpus": gpu_temps,
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


def resource_uptime() -> dict:
    inv = get_inventory(include_pci=False)
    vit = get_vitals()
    s = inv.get("summary") or {}
    secs = s.get("uptime_seconds")
    if secs is None:
        # From OS component if present
        for c in inv.get("components", []):
            if c.get("category") == "os" and c.get("uptime_seconds") is not None:
                secs = c.get("uptime_seconds")
                break
    if secs is None and vit.get("boot_time"):
        import time as _time

        try:
            secs = max(0.0, _time.time() - float(vit["boot_time"]))
        except (TypeError, ValueError):
            secs = None
    return _ok(
        "uptime",
        {
            "uptime_seconds": secs,
            "human": _fmt_uptime(secs),
            "boot_time": vit.get("boot_time"),
        },
    )


def resource_version() -> dict:
    from backend.version import NAME, VERSION

    return _ok(
        "version",
        {
            "name": NAME,
            "version": VERSION,
            "cli": "si · sysinspect",
        },
    )


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


def resource_fans() -> dict:
    vit = get_vitals()
    fans = vit.get("fans") or []
    return _ok(
        "fans",
        {
            "available": bool(fans),
            "fans": fans,
            "note": None if fans else "No fan RPM/PWM reported (common on locked laptop EC).",
        },
    )


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
            "fans": resource_fans()["data"],
            "uptime": resource_uptime()["data"],
            "version": resource_version()["data"],
        },
    )


HANDLERS: dict[str, Callable[..., dict]] = {
    "status": resource_status,
    "cpu": resource_cpu,
    "gpu": resource_gpu,
    "memory": resource_memory,
    "temps": resource_temps,
    "fans": resource_fans,
    "board": resource_board,
    "os": resource_os,
    "disk": resource_disk,
    "net": resource_net,
    "battery": resource_battery,
    "scan": resource_scan,
    "uptime": resource_uptime,
    "version": resource_version,
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
    """Narrow a resource payload by field filters (temp, usage, name, kernel, …)."""
    if not payload.get("ok") or not fields:
        return payload
    resource = payload.get("resource")
    data = payload.get("data")
    if data is None:
        return payload

    filtered: Any = data
    os_detail = fields & _OS_DETAIL_FIELDS

    # OS slices first (si os version, si kernel, …)
    if resource == "os" and os_detail and not (fields & {"temp", "usage"}):
        filtered = _filter_os(data, fields)
    else:
        if "temp" in fields:
            filtered = _filter_temp(resource, data)
        if "usage" in fields:
            filtered = _filter_usage(resource, filtered if "temp" not in fields else data)
            if "temp" in fields:
                t = _filter_temp(resource, data)
                u = _filter_usage(resource, data)
                filtered = {"temp": t, "usage": u}
        if "name" in fields and "temp" not in fields and "usage" not in fields and resource != "os":
            filtered = _filter_name(resource, data)
        if "name" in fields and resource == "os" and not os_detail - {"name"}:
            filtered = _filter_os(data, {"name"} | (fields & _OS_DETAIL_FIELDS))
        if "summary" in fields and len(fields) == 1:
            filtered = _filter_summary(resource, data)

    out = dict(payload)
    out["data"] = filtered
    out["fields"] = sorted(fields)
    return out


def _filter_os(data: dict, fields: set[str]) -> dict:
    """Pick only requested OS lines (smart slices)."""
    out: dict[str, Any] = {}
    if "version" in fields or "name" in fields:
        out["pretty_name"] = data.get("pretty_name") or data.get("name")
    if "kernel" in fields:
        out["kernel"] = data.get("kernel") or data.get("release")
    if "hostname" in fields:
        out["hostname"] = data.get("hostname")
    if "desktop" in fields:
        out["desktop_environment"] = data.get("desktop_environment")
        out["session_type"] = data.get("session_type")
    if "arch" in fields:
        out["architecture"] = data.get("architecture") or data.get("machine")
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
        gpus = d.get("gpus") or []
        gpus_s = ", ".join(_short_gpu(g) for g in gpus) if gpus else "—"
        lines = [
            f"{d.get('hostname') or 'host'}  ·  {d.get('os') or '—'}",
            f"CPU  {d.get('cpu') or '—'}",
            f"GPU  {gpus_s}",
            f"RAM  {d.get('ram_gb')} GB",
            f"Live  CPU {_pct(live.get('cpu_percent'))}  ·  "
            f"GPU {_pct(live.get('gpu_percent'))}  ·  "
            f"RAM {_pct(live.get('ram_percent'))}",
            f"Temps  CPU {_deg(live.get('cpu_temp_c'))}  ·  GPU {_deg(live.get('gpu_temp_c'))}",
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
                lines.append(f"  {_short_gpu(g.get('name')):28}  {_deg(g.get('temp_c'))}")
            return "\n".join(lines)
        if fields == {"name"}:
            return "GPU\n" + "\n".join(f"  {_short_gpu(g.get('name'))}" for g in devices)
        if fields == {"usage"}:
            lines = ["GPU load"]
            for g in devices:
                lines.append(
                    f"  {_short_gpu(g.get('name')):28}  {_pct(g.get('usage_percent'))}  ·  "
                    f"VRAM {g.get('vram_used_mb') or '—'} / {g.get('vram_total_mb') or '—'} MB"
                )
            return "\n".join(lines)
        lines = ["GPU"]
        for g in devices:
            lines.append(f"  {_short_gpu(g.get('name'))}")
            lines.append(
                f"    Load {_pct(g.get('usage_percent'))}  ·  Temp {_deg(g.get('temp_c'))}  ·  "
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
            lines.append(
                f"       GPU {_short_gpu(g.get('name')):28}  {_deg(g.get('temp_c'))}".rstrip()
            )
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
                lines.append(f"  {label:28}  {_pct(f.get('percent'))}")
            else:
                lines.append(f"  {label}")
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
        # Filtered one-liners
        if fields & _OS_DETAIL_FIELDS:
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
        return (
            f"OS       {d.get('name') or d.get('pretty_name') or '—'}\n"
            f"Kernel   {d.get('kernel') or d.get('release') or '—'}\n"
            f"Host     {d.get('hostname') or '—'}\n"
            f"Desktop  {d.get('desktop_environment') or '—'}  ·  "
            f"{d.get('session_type') or '—'}\n"
            f"Arch     {d.get('architecture') or '—'}"
        )

    if r == "uptime":
        return f"Uptime   {d.get('human') or _fmt_uptime(d.get('uptime_seconds'))}"

    if r == "version":
        return f"{d.get('name') or 'System Inspector'}  {d.get('version') or '—'}\nCLI      {d.get('cli') or 'si'}"

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


def _fmt_uptime(secs: Any) -> str:
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


def list_commands_help() -> str:
    return """
sysinspect — System Inspector CLI
=================================
Also installable as:  si

USAGE
  sysinspect <resource> [resource…] [field…] [options]
  sysinspect watch|graph|live <resource> [field…] [--interval 1]
  sysinspect help

RESOURCES
  status, summary          Quick host + live overview
  cpu, processor           CPU model, load, freq, temp
  gpu, graphics, nvidia    GPU(s): load, VRAM, temp, power
  ram, memory, mem         Memory / swap
  temp, temps, thermal     CPU + GPU temperatures
  fans, fan, cooling       Fan RPM / PWM when reported
  board, motherboard, mb   System / motherboard / BIOS
  os, system, host         Full OS block
  uptime, up               How long the machine has been on
  version, ver, about      This app's version (System Inspector)
  disk, storage, ssd       Disks, partitions, I/O rates
  net, network, wifi       Interfaces + throughput
  battery, bat             Laptop battery if present
  scan, inventory, hw      Hardware inventory summary
  all, everything          Big combined snapshot

FIELDS (narrow the answer — e.g. si os version, si kernel)
  temp, temperature        Temperatures only
  usage, util, load        Utilization only
  name, model              Names/models only
  kernel                   Kernel string only (si kernel)
  version                  With os: distro name only (si os version)
  hostname                 Hostname only
  desktop, de              Desktop session
  arch                     Architecture

EXAMPLES
  si gpu
  si cpu temp
  si temps
  si os version            → Pop!_OS …
  si kernel                → kernel line only
  si uptime
  si version               → System Inspector 0.x
  si live cpu gpu
  si status --plain

OPTIONS
  --json, -j          Machine-readable JSON
  --plain, -p         Text only: no banner, colors, meters
  --pci               Include full PCI list (scan only)
  --interval N        Seconds between watch updates (default 1)
  --graph             Watch: also show optional line charts
""".strip()

