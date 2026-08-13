from __future__ import annotations

import platform
import re
from pathlib import Path

import psutil

from .util import read_text, run_cmd, safe_dict


def collect_cpu_inventory() -> dict:
    brand = _cpu_brand()
    freqs = psutil.cpu_freq()
    flags = _cpu_flags()

    return safe_dict(
        category="cpu",
        name=brand,
        brand=brand,
        architecture=platform.machine(),
        bits=platform.architecture()[0],
        vendor_id=_cpuinfo_field("vendor_id"),
        family=_cpuinfo_field("cpu family"),
        model=_cpuinfo_field("model"),
        stepping=_cpuinfo_field("stepping"),
        microcode=_cpuinfo_field("microcode"),
        cores_physical=psutil.cpu_count(logical=False),
        cores_logical=psutil.cpu_count(logical=True),
        freq_min_mhz=round(freqs.min, 2) if freqs and freqs.min else None,
        freq_max_mhz=round(freqs.max, 2) if freqs and freqs.max else None,
        freq_current_mhz=round(freqs.current, 2) if freqs and freqs.current else None,
        cache_l1d=_sysfs_cache("index0"),
        cache_l1i=_sysfs_cache("index1"),
        cache_l2=_sysfs_cache("index2"),
        cache_l3=_sysfs_cache("index3"),
        flags=flags[:40] if flags else None,
        flag_count=len(flags) if flags else None,
        lscpu=_lscpu_summary(),
    )


def collect_cpu_vitals() -> dict:
    freqs = psutil.cpu_freq()
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    load = psutil.getloadavg() if hasattr(psutil, "getloadavg") else None

    return safe_dict(
        usage_percent=psutil.cpu_percent(interval=None),
        usage_per_core=per_core,
        freq_current_mhz=round(freqs.current, 2) if freqs and freqs.current else None,
        load_1m=round(load[0], 2) if load else None,
        load_5m=round(load[1], 2) if load else None,
        load_15m=round(load[2], 2) if load else None,
        temperatures=_cpu_temperatures(),
    )


def _cpu_brand() -> str:
    brand = _cpuinfo_field("model name") or platform.processor()
    if brand and brand.strip() and brand != "unknown":
        return brand.strip()

    lscpu = run_cmd(["lscpu"])
    if lscpu:
        for line in lscpu.splitlines():
            if line.lower().startswith("model name:"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "Unknown CPU"


def _cpuinfo_field(key: str) -> str | None:
    raw = read_text("/proc/cpuinfo")
    if not raw:
        return None
    pattern = re.compile(rf"^{re.escape(key)}\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(raw)
    return match.group(1).strip() if match else None


def _cpu_flags() -> list[str]:
    flags = _cpuinfo_field("flags")
    if not flags:
        return []
    return flags.split()


def _sysfs_cache(index: str) -> str | None:
    base = Path(f"/sys/devices/system/cpu/cpu0/cache/{index}")
    if not base.is_dir():
        return None
    size = read_text(base / "size")
    level = read_text(base / "level")
    ctype = read_text(base / "type")
    if not size:
        return None
    parts = [f"L{level}" if level else index, ctype, size]
    return " ".join(p for p in parts if p)


def _lscpu_summary() -> dict | None:
    raw = run_cmd(["lscpu", "--json"])
    if raw:
        import json

        try:
            data = json.loads(raw)
            fields = {
                item["field"].rstrip(":"): item["data"]
                for item in data.get("lscpu", [])
                if "field" in item and "data" in item
            }
            # Keep a short useful subset
            keys = [
                "Architecture",
                "CPU op-mode(s)",
                "Vendor ID",
                "Model name",
                "CPU(s)",
                "Thread(s) per core",
                "Core(s) per socket",
                "Socket(s)",
                "CPU max MHz",
                "CPU min MHz",
                "L1d cache",
                "L1i cache",
                "L2 cache",
                "L3 cache",
                "Vulnerability Spectre v2",
            ]
            return {k: fields[k] for k in keys if k in fields} or fields
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    raw = run_cmd(["lscpu"])
    if not raw:
        return None
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out or None


def _cpu_temperatures() -> list[dict]:
    temps: list[dict] = []
    readings = psutil.sensors_temperatures(fahrenheit=False) or {}
    preferred = ("k10temp", "coretemp", "zenpower", "acpitz", "cpu_thermal")
    for name in preferred:
        if name not in readings:
            continue
        for entry in readings[name]:
            temps.append(
                safe_dict(
                    sensor=name,
                    label=entry.label or name,
                    celsius=round(entry.current, 1) if entry.current is not None else None,
                    high=round(entry.high, 1) if entry.high is not None else None,
                    critical=round(entry.critical, 1) if entry.critical is not None else None,
                )
            )
    if temps:
        return temps

    # Fallback: any thermal zone that looks like CPU
    for name, entries in readings.items():
        for entry in entries:
            label = (entry.label or name).lower()
            if "cpu" in label or "tctl" in label or "tdie" in label or "package" in label:
                temps.append(
                    safe_dict(
                        sensor=name,
                        label=entry.label or name,
                        celsius=round(entry.current, 1) if entry.current is not None else None,
                    )
                )
    return temps
