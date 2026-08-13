from __future__ import annotations

from pathlib import Path

import psutil

from .util import bytes_to_gb, read_text, safe_dict


def collect_memory_inventory() -> list[dict]:
    """Return RAM module-ish summary + swap as inventory items."""
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    modules = _dmi_memory_modules()

    items: list[dict] = [
        safe_dict(
            category="memory",
            name=f"System RAM ({bytes_to_gb(vm.total)} GB)",
            total_bytes=vm.total,
            total_gb=bytes_to_gb(vm.total),
            available_gb=bytes_to_gb(vm.available),
            modules=modules or None,
            module_count=len(modules) if modules else None,
        )
    ]

    if sm.total:
        items.append(
            safe_dict(
                category="swap",
                name=f"Swap ({bytes_to_gb(sm.total)} GB)",
                total_bytes=sm.total,
                total_gb=bytes_to_gb(sm.total),
            )
        )
    return items


def collect_memory_vitals() -> dict:
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    return safe_dict(
        ram=safe_dict(
            total_bytes=vm.total,
            used_bytes=vm.used,
            available_bytes=vm.available,
            percent=vm.percent,
            total_gb=bytes_to_gb(vm.total),
            used_gb=bytes_to_gb(vm.used),
            available_gb=bytes_to_gb(vm.available),
        ),
        swap=safe_dict(
            total_bytes=sm.total,
            used_bytes=sm.used,
            percent=sm.percent,
            total_gb=bytes_to_gb(sm.total),
            used_gb=bytes_to_gb(sm.used),
        ),
    )


def _dmi_memory_modules() -> list[dict]:
    """Best-effort DIMM info from DMI (often needs root for dmidecode)."""
    from .util import run_cmd

    raw = run_cmd(["dmidecode", "-t", "memory"])
    if not raw:
        # sysfs meminfo bits
        return _meminfo_summary()

    modules: list[dict] = []
    block: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("Memory Device"):
            if block.get("Size") and block["Size"] not in ("No Module Installed", "Not Installed"):
                modules.append(_normalize_dmi_module(block))
            block = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            block[k.strip()] = v.strip()
    if block.get("Size") and block["Size"] not in ("No Module Installed", "Not Installed"):
        modules.append(_normalize_dmi_module(block))
    return modules or _meminfo_summary()


def _normalize_dmi_module(block: dict[str, str]) -> dict:
    return safe_dict(
        size=block.get("Size"),
        type=block.get("Type"),
        speed=block.get("Speed"),
        configured_speed=block.get("Configured Memory Speed") or block.get("Configured Clock Speed"),
        manufacturer=block.get("Manufacturer"),
        part_number=block.get("Part Number"),
        serial=block.get("Serial Number"),
        locator=block.get("Locator"),
        form_factor=block.get("Form Factor"),
    )


def _meminfo_summary() -> list[dict]:
    raw = read_text("/proc/meminfo")
    if not raw:
        return []
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields[k] = v.strip()
    return [
        safe_dict(
            source="/proc/meminfo",
            mem_total=fields.get("MemTotal"),
            mem_available=fields.get("MemAvailable"),
            hugepages_total=fields.get("HugePages_Total"),
        )
    ]
