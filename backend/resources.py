"""
Resource payloads: handlers, field filters, run_query.

What people type is parsed in backend/query.py; this file builds the dicts.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any, Callable

from backend.collectors import get_inventory
from backend.collectors.gpu import normalize_pci_bdf, short_gpu_name as _short_gpu
from backend.collectors.os_info import uptime_seconds
from backend.fields import NET_DETAIL_FIELDS, OS_DETAIL_FIELDS
from backend.query import ALIASES, CANONICAL, parse_query, vitals_needs_for
from backend.snapshot import Snapshot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(resource: str, data: Any, **extra: Any) -> dict:
    # Deep copy so Snapshot-cached dicts can't be mutated by format/TUI paths.
    out = {"ok": True, "at": _now(), "resource": resource, "data": copy.deepcopy(data)}
    out.update(extra)
    return out


# ---------- resource builders ----------

_NVIDIA_MARKERS = ("nvidia", "geforce", "rtx", "quadro", "tesla")


def _is_nvidia_gpu(vendor: str | None, name: str | None) -> bool:
    hay = f"{vendor or ''} {name or ''}".lower()
    return any(m in hay for m in _NVIDIA_MARKERS)


def _text_has_nvidia(text: str) -> bool:
    hay = text.lower()
    return any(m in hay for m in _NVIDIA_MARKERS)


def resource_status(snap: Snapshot) -> dict:
    inv = snap.inventory()
    vit = snap.vitals()
    s = inv.get("summary") or {}
    cpu = vit.get("cpu") or {}
    mem = vit.get("memory") or {}
    ram = mem.get("ram") or {}
    swap = mem.get("swap") or {}
    rates = vit.get("rates") or {}
    bat = vit.get("battery")
    gpus = vit.get("gpus") or []
    # Prefer discrete NVIDIA for the summary "GPU" slots when multi-GPU
    g0 = next(
        (g for g in gpus if _is_nvidia_gpu(g.get("vendor"), g.get("name"))),
        None,
    )
    if g0 is None:
        g0 = gpus[0] if gpus else {}
    # Inventory-only NVIDIA (no NVML) still shows up in summary gpus names
    gpu_note = None
    inv_gpu_names = " ".join(str(x) for x in (s.get("gpus") or [])).lower()
    has_nvidia_inv = _text_has_nvidia(inv_gpu_names)
    has_nvidia_live = any(_is_nvidia_gpu(g.get("vendor"), g.get("name")) for g in gpus)
    if has_nvidia_inv and not has_nvidia_live:
        gpu_note = "NVIDIA · driver/NVML unavailable"
    elif g0:
        gpu_note = gpu_sensor_note(
            {
                "vendor": g0.get("vendor"),
                "source": g0.get("source"),
                "usage_percent": g0.get("usage_percent"),
                "temp_c": g0.get("temperature_c"),
                "vram_total_mb": g0.get("vram_total_mb"),
            }
        )
    elif s.get("gpus"):
        gpu_note = "GPU listed · no live sensors yet"
    up_secs = uptime_seconds()
    if up_secs is None:
        up_secs = s.get("uptime_seconds")
    return _ok(
        "status",
        {
            "hostname": s.get("hostname"),
            "os": s.get("os"),
            "cpu": s.get("cpu"),
            "gpus": s.get("gpus"),
            "ram_gb": s.get("ram_gb"),
            "uptime_seconds": up_secs,
            "live": {
                "cpu_percent": cpu.get("usage_percent"),
                "cpu_temp_c": _cpu_temp(cpu),
                "cpu_freq_mhz": cpu.get("freq_current_mhz"),
                "load_1m": cpu.get("load_1m"),
                "gpu_percent": g0.get("usage_percent"),
                "gpu_temp_c": g0.get("temperature_c"),
                "gpu_power_w": g0.get("power_watts"),
                "gpu_power_limit_w": g0.get("power_limit_watts"),
                "gpu_vram_used_mb": g0.get("vram_used_mb"),
                "gpu_vram_total_mb": g0.get("vram_total_mb"),
                "gpu_clock_mhz": g0.get("graphics_mhz"),
                "ram_percent": ram.get("percent"),
                "ram_used_gb": ram.get("used_gb"),
                "ram_total_gb": ram.get("total_gb"),
                "swap_percent": swap.get("percent"),
                "swap_used_gb": swap.get("used_gb"),
                "swap_total_gb": swap.get("total_gb"),
                "disk_read_mbs": rates.get("disk_read_mbs"),
                "disk_write_mbs": rates.get("disk_write_mbs"),
                "net_recv_mbs": rates.get("net_recv_mbs"),
                "net_sent_mbs": rates.get("net_sent_mbs"),
                "rates_ready": bool(rates.get("ready")),
                "battery_percent": (bat or {}).get("percent") if bat else None,
                "battery_plugged": (bat or {}).get("power_plugged") if bat else None,
                "gpu_note": gpu_note,
            },
        },
    )


def resource_cpu(snap: Snapshot) -> dict:
    inv = snap.inventory()
    vit = snap.vitals()
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


def gpu_sensor_note(g: dict) -> str | None:
    """Human reason when a GPU is visible but stats are missing — not just '—'."""
    usage = g.get("usage_percent")
    temp = g.get("temp_c")
    if temp is None:
        temp = g.get("temperature_c")
    vram = g.get("vram_total_mb")
    source = (g.get("source") or "").lower()
    vendor = (g.get("vendor") or "").lower()
    has_any = usage is not None or temp is not None or vram is not None
    if has_any and usage is not None:
        return None
    if source == "lspci" or (not has_any and "nvidia" in vendor):
        if "nvidia" in vendor:
            return "PCI only · NVIDIA driver/NVML unavailable"
        return "PCI only · no live sensors"
    if source == "hwmon" and usage is None:
        if temp is not None:
            return "temp via hwmon · load not reported"
        return "hwmon · limited sensors"
    if not has_any:
        return "no live sensors"
    if usage is None and temp is not None:
        return "load not reported"
    return None


def _pci_dev_id(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"([0-9a-f]{4}:[0-9a-f]{4})", str(value).lower())
    return m.group(1) if m else None


def _inv_gpu_keys(g: dict) -> set[str]:
    keys: set[str] = set()
    if g.get("index") is not None:
        keys.add(f"idx:{g['index']}")
    slot = normalize_pci_bdf(g.get("pci_slot") or g.get("pci_bus_id"))
    if slot:
        keys.add(f"bdf:{slot}")
    dev_id = _pci_dev_id(g.get("pci_id"))
    if dev_id:
        keys.add(f"dev:{dev_id}")
    return keys


def _live_gpu_keys(lg: dict) -> set[str]:
    keys: set[str] = set()
    if lg.get("index") is not None:
        keys.add(f"idx:{lg['index']}")
    slot = normalize_pci_bdf(lg.get("pci_bus_id") or lg.get("pci_slot"))
    if slot:
        keys.add(f"bdf:{slot}")
    dev_id = _pci_dev_id(lg.get("pci_id"))
    if dev_id:
        keys.add(f"dev:{dev_id}")
    return keys


def _match_live_by_id(g: dict, live: list[dict], used_live: set[int]) -> dict | None:
    want = _inv_gpu_keys(g)
    if not want:
        return None
    for i, lg in enumerate(live):
        if i in used_live:
            continue
        overlap = want & _live_gpu_keys(lg)
        if not overlap:
            continue
        if any(k.startswith("bdf:") for k in overlap):
            used_live.add(i)
            return lg
        if g.get("index") is not None and f"idx:{g.get('index')}" in overlap:
            used_live.add(i)
            return lg
        if any(k.startswith("idx:") for k in overlap):
            used_live.add(i)
            return lg
    return None


def _match_live_by_name(g: dict, live: list[dict], used_live: set[int]) -> dict:
    g_vendor = (g.get("vendor") or "").lower()
    g_name = (g.get("name") or "").lower()
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
                if (
                    "nvidia" in g_vendor
                    and "nvidia" not in lv
                    and "nvidia" not in ln
                    and "nv" not in ln
                ):
                    continue
                used_live.add(i)
                return lg
    for i, lg in enumerate(live):
        if i in used_live:
            continue
        ln = (lg.get("name") or "").lower()
        if ln and (
            ln in g_name
            or g_name in ln
            or any(tok in ln for tok in re.findall(r"[a-z0-9]{4,}", g_name) if len(tok) > 4)
        ):
            used_live.add(i)
            return lg
    return {}


def _device_from_pair(g: dict, live_g: dict) -> dict:
    device = {
        "name": _short_gpu(g.get("name") or live_g.get("name")),
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
        "pci_slot": g.get("pci_slot"),
        "source": live_g.get("source") or g.get("source"),
    }
    device["note"] = gpu_sensor_note(device)
    return device


def _device_from_live_only(lg: dict) -> dict:
    device = {
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
    device["note"] = gpu_sensor_note(device)
    return device


def merge_gpu_devices(inv: dict, vit: dict) -> list[dict]:
    """Join static GPU inventory with live sensor readings."""
    inv_gpus = [c for c in inv.get("components", []) if c.get("category") == "gpu"]
    live = list(vit.get("gpus") or [])
    used_live: set[int] = set()
    devices: list[dict] = []

    for g in inv_gpus:
        live_g = _match_live_by_id(g, live, used_live)
        if live_g is None:
            live_g = _match_live_by_name(g, live, used_live)
        devices.append(_device_from_pair(g, live_g or {}))

    for i, lg in enumerate(live):
        if i in used_live:
            continue
        devices.append(_device_from_live_only(lg))

    if not devices and live:
        devices = [_device_from_live_only(lg) for lg in live]
    return devices


def resource_gpu(snap: Snapshot) -> dict:
    inv = snap.inventory()
    vit = snap.vitals()
    devices = merge_gpu_devices(inv, vit)
    return _ok("gpu", {"count": len(devices), "devices": devices})


def resource_memory(snap: Snapshot) -> dict:
    vit = snap.vitals()
    mem = vit.get("memory") or {}
    return _ok("memory", mem)


def resource_temps(snap: Snapshot) -> dict:
    vit = snap.vitals()
    cpu = vit.get("cpu") or {}
    devices = merge_gpu_devices(snap.inventory(), vit)
    gpu_temps = [
        {
            "name": g.get("name"),
            "temp_c": g.get("temp_c"),
            "note": g.get("note") if g.get("temp_c") is None else None,
        }
        for g in devices
    ]
    if not gpu_temps:
        gpus = vit.get("gpus") or []
        gpu_temps = [
            {
                "name": _short_gpu(g.get("name")),
                "temp_c": g.get("temperature_c"),
                "note": gpu_sensor_note(
                    {
                        "vendor": g.get("vendor"),
                        "source": g.get("source"),
                        "usage_percent": g.get("usage_percent"),
                        "temp_c": g.get("temperature_c"),
                        "vram_total_mb": g.get("vram_total_mb"),
                    }
                )
                if g.get("temperature_c") is None
                else None,
            }
            for g in gpus
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


def resource_board(snap: Snapshot) -> dict:
    inv = snap.inventory()
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


def resource_os(snap: Snapshot) -> dict:
    inv = snap.inventory()
    for c in inv.get("components", []):
        if c.get("category") == "os":
            return _ok("os", c)
    return _ok("os", inv.get("summary") or {})


def resource_uptime(snap: Snapshot) -> dict:
    from backend.format import fmt_uptime as __fmt_uptime

    inv = snap.inventory()
    vit = snap.vitals()
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
            "human": __fmt_uptime(secs),
            "boot_time": vit.get("boot_time"),
        },
    )


def resource_version(_snap: Snapshot) -> dict:
    from backend.version import NAME, VERSION

    return _ok(
        "version",
        {
            "name": NAME,
            "version": VERSION,
            "cli": "si · sysinspect",
        },
    )


def resource_disk(snap: Snapshot) -> dict:
    inv = snap.inventory()
    vit = snap.vitals()
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


def resource_net(snap: Snapshot) -> dict:
    from backend.collectors.network import collect_net_static

    inv = snap.inventory()
    vit = snap.vitals()
    nets = [
        c
        for c in inv.get("components", [])
        if c.get("category") in ("network", "network_controller")
    ]
    rates = vit.get("rates") or {}
    static = collect_net_static()
    return _ok(
        "net",
        {
            "interfaces": nets,
            "rates_mbs": {
                "recv": rates.get("net_recv_mbs"),
                "sent": rates.get("net_sent_mbs"),
            },
            "totals": (vit.get("network") or {}).get("total"),
            "addresses": static.get("addresses"),
            "gateway": static.get("gateway"),
            "dns": static.get("dns"),
        },
    )


def resource_battery(snap: Snapshot) -> dict:
    vit = snap.vitals()
    bat = vit.get("battery")
    if not bat:
        return _ok("battery", {"present": False, "note": "No battery detected (desktop or sensor missing)."})
    return _ok("battery", {"present": True, **bat})


def resource_fans(snap: Snapshot) -> dict:
    vit = snap.vitals()
    fans = vit.get("fans") or []
    return _ok(
        "fans",
        {
            "available": bool(fans),
            "fans": fans,
            "note": None if fans else "No fan RPM/PWM reported (common on locked laptop EC).",
        },
    )


def resource_scan(snap: Snapshot, include_pci: bool = False) -> dict:
    if include_pci == snap.include_pci:
        inv = snap.inventory()
    else:
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


def resource_all(snap: Snapshot) -> dict:
    sections: dict[str, Any] = {}
    for name, handler in (
        ("status", resource_status),
        ("cpu", resource_cpu),
        ("gpu", resource_gpu),
        ("memory", resource_memory),
        ("temps", resource_temps),
        ("board", resource_board),
        ("os", resource_os),
        ("disk", resource_disk),
        ("net", resource_net),
        ("battery", resource_battery),
        ("fans", resource_fans),
        ("uptime", resource_uptime),
        ("version", resource_version),
    ):
        try:
            payload = handler(snap)
            if payload.get("ok"):
                sections[name] = payload.get("data")
            else:
                sections[name] = payload
        except Exception as exc:
            sections[name] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return _ok("all", sections)


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


def get_resource(name: str, snap: Snapshot, **kwargs: Any) -> dict:
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
        return handler(snap, include_pci=bool(kwargs.get("include_pci", False)))
    return handler(snap)


def apply_fields(payload: dict, fields: set[str], *, snap: Snapshot | None = None) -> dict:
    """Narrow a resource payload by field filters (temp, usage, name, kernel, …)."""
    if not payload.get("ok") or not fields:
        return payload
    resource = payload.get("resource")
    data = payload.get("data")
    if data is None:
        return payload

    filtered: Any = data
    os_detail = fields & OS_DETAIL_FIELDS
    net_detail = fields & NET_DETAIL_FIELDS

    # OS slices first (si os version, si kernel, …)
    if resource == "os" and os_detail and not (fields & {"temp", "usage"}):
        filtered = _filter_os(data, fields)
    elif resource == "net" and net_detail:
        filtered = _filter_net(data, fields, snap)
    else:
        if "temp" in fields and "usage" in fields:
            filtered = {
                "temp": _filter_temp(resource, data),
                "usage": _filter_usage(resource, data),
            }
        elif "temp" in fields:
            filtered = _filter_temp(resource, data)
        elif "usage" in fields:
            filtered = _filter_usage(resource, data)
        if "name" in fields and "temp" not in fields and "usage" not in fields and resource != "os":
            filtered = _filter_name(resource, data)
        if "name" in fields and resource == "os" and not os_detail - {"name"}:
            filtered = _filter_os(data, {"name"} | (fields & OS_DETAIL_FIELDS))
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


def _filter_net(data: dict, fields: set[str], snap: Snapshot | None) -> dict:
    """Pick only requested network slices (si net ip, si net connections, …)."""
    out: dict[str, Any] = {}
    if "ip" in fields:
        out["addresses"] = data.get("addresses") or []
    if "gateway" in fields:
        out["gateway"] = data.get("gateway") or {}
    if "dns" in fields:
        out["dns"] = data.get("dns") or {}
    if snap is None:
        return out

    if "connections" in fields:
        out["connections"] = snap.net_connections()
    if "listen" in fields:
        out["listeners"] = snap.net_listeners()
    if "routes" in fields:
        out["routes"] = snap.net_routes()
    if "wifi" in fields:
        out["wifi"] = snap.net_wifi()
    if "public" in fields:
        out["public"] = snap.net_public_ip()
    return out


def _filter_temp(resource: str | None, data: Any) -> Any:
    if resource == "cpu":
        return {"temp_c": data.get("temp_c"), "temperatures": data.get("temperatures")}
    if resource == "gpu":
        devices = data.get("devices") or []
        return {
            "devices": [
                {
                    "name": d.get("name"),
                    "temp_c": d.get("temp_c"),
                    "note": d.get("note"),
                }
                for d in devices
            ],
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
                    "note": d.get("note"),
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


def run_query(tokens: list[str], *, snap: Snapshot | None = None, **kwargs: Any) -> dict:
    """
    Execute freeform tokens. Returns single resource payload or multi bundle.

    Pass an existing Snapshot to reuse inventory across live ticks.
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

    if snap is None:
        snap = Snapshot(
            include_pci=bool(kwargs.get("include_pci", False)),
            verbose=bool(kwargs.get("verbose", False)),
            vitals_needs=vitals_needs_for(resources),
        )
    else:
        snap.vitals_needs = vitals_needs_for(resources)
    results = []
    for r in resources:
        try:
            payload = get_resource(r, snap, **kwargs)
            payload = apply_fields(payload, fields, snap=snap)
            if unknown:
                payload["unknown_tokens"] = unknown
            results.append(payload)
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "at": _now(),
                    "resource": r,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    if len(results) == 1:
        out = results[0]
        if kwargs.get("verbose"):
            out["verbose"] = True
        return out
    out = {
        "ok": all(r.get("ok") for r in results),
        "at": _now(),
        "resource": "bundle",
        "query": tokens,
        "fields": sorted(fields),
        "results": results,
    }
    if kwargs.get("verbose"):
        out["verbose"] = True
    return out


def _cpu_temp(cpu: dict) -> float | None:
    temps = cpu.get("temperatures") or []
    if temps and temps[0].get("celsius") is not None:
        return temps[0]["celsius"]
    return None
