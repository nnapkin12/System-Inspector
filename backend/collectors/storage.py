from __future__ import annotations

from pathlib import Path

import psutil

from .util import bytes_to_gb, read_text, safe_dict


def collect_storage_inventory() -> list[dict]:
    items: list[dict] = []

    # Block devices /sys
    for device in sorted(Path("/sys/block").glob("*")):
        name = device.name
        if name.startswith(("loop", "ram", "dm-", "zram")):
            continue
        size_sectors = read_text(device / "size")
        size_bytes = None
        if size_sectors and size_sectors.isdigit():
            # sector size usually 512 in this sysfs size file
            size_bytes = int(size_sectors) * 512
        model = read_text(device / "device" / "model")
        vendor = read_text(device / "device" / "vendor")
        rev = read_text(device / "device" / "rev")
        rotational = read_text(device / "queue" / "rotational")
        kind = "HDD" if rotational == "1" else "SSD/NVMe" if rotational == "0" else None
        items.append(
            safe_dict(
                category="disk",
                name=(model or name).strip() if model else name,
                device=f"/dev/{name}",
                model=model.strip() if model else None,
                vendor=vendor.strip() if vendor else None,
                revision=rev.strip() if rev else None,
                media=kind,
                size_bytes=size_bytes,
                size_gb=bytes_to_gb(size_bytes) if size_bytes else None,
                source="sysfs",
            )
        )

    # Mounted partitions
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        items.append(
            safe_dict(
                category="partition",
                name=f"{part.device} → {part.mountpoint}",
                device=part.device,
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                opts=part.opts,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                total_gb=bytes_to_gb(usage.total),
                used_gb=bytes_to_gb(usage.used),
                free_gb=bytes_to_gb(usage.free),
                percent=usage.percent,
            )
        )

    return items


def collect_storage_vitals() -> dict:
    counters = psutil.disk_io_counters(perdisk=False)
    partitions = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        partitions.append(
            safe_dict(
                device=part.device,
                mountpoint=part.mountpoint,
                percent=usage.percent,
                used_gb=bytes_to_gb(usage.used),
                total_gb=bytes_to_gb(usage.total),
            )
        )

    io = None
    if counters:
        io = safe_dict(
            read_bytes=counters.read_bytes,
            write_bytes=counters.write_bytes,
            read_count=counters.read_count,
            write_count=counters.write_count,
        )

    return safe_dict(partitions=partitions, io=io)
