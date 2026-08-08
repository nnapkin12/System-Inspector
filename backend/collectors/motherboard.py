from __future__ import annotations

from pathlib import Path

from .util import read_text, run_cmd, safe_dict

DMI = Path("/sys/class/dmi/id")


def collect_board() -> list[dict]:
    items: list[dict] = []

    product = _dmi("product_name")
    vendor = _dmi("sys_vendor")
    version = _dmi("product_version")
    serial = _dmi("product_serial")
    sku = _dmi("product_sku")
    uuid = _dmi("product_uuid")

    items.append(
        safe_dict(
            category="system",
            name=" ".join(p for p in (vendor, product) if p) or "System",
            vendor=vendor,
            product=product,
            version=version,
            serial=_redact_serial(serial),
            sku=sku,
            uuid=_redact_serial(uuid),
            family=_dmi("product_family"),
            source="dmi",
        )
    )

    board_name = _dmi("board_name")
    board_vendor = _dmi("board_vendor")
    items.append(
        safe_dict(
            category="motherboard",
            name=" ".join(p for p in (board_vendor, board_name) if p) or "Motherboard",
            vendor=board_vendor,
            product=board_name,
            version=_dmi("board_version"),
            serial=_redact_serial(_dmi("board_serial")),
            asset_tag=_dmi("board_asset_tag"),
            source="dmi",
        )
    )

    bios_vendor = _dmi("bios_vendor")
    bios_version = _dmi("bios_version")
    items.append(
        safe_dict(
            category="bios",
            name=f"{bios_vendor or 'BIOS'} {bios_version or ''}".strip(),
            vendor=bios_vendor,
            version=bios_version,
            date=_dmi("bios_date"),
            release=_dmi("bios_release"),
            source="dmi",
        )
    )

    chassis = _dmi("chassis_type")
    items.append(
        safe_dict(
            category="chassis",
            name=_dmi("chassis_version") or "Chassis",
            vendor=_dmi("chassis_vendor"),
            type=chassis,
            serial=_redact_serial(_dmi("chassis_serial")),
            source="dmi",
        )
    )

    # Battery if laptop
    battery = _battery()
    if battery:
        items.append(battery)

    return items


def _dmi(field: str) -> str | None:
    value = read_text(DMI / field)
    if not value or value == "Default string" or value == "None":
        return None
    return value


def _redact_serial(value: str | None) -> str | None:
    """Keep presence of serial without fully exposing it in UI JSON dumps optionally.
    For a local diagnostic tool we still show it; user can remove later.
    """
    return value


def _battery() -> dict | None:
    try:
        import psutil
    except ImportError:
        return None
    if not hasattr(psutil, "sensors_battery"):
        return None
    bat = psutil.sensors_battery()
    if bat is None:
        return None
    return safe_dict(
        category="battery",
        name="Battery",
        percent=bat.percent,
        secs_left=bat.secsleft if bat.secsleft and bat.secsleft > 0 else None,
        power_plugged=bat.power_plugged,
        source="psutil",
    )


def collect_pci_devices() -> list[dict]:
    raw = run_cmd(["lspci", "-nn"])
    if not raw:
        return []
    devices = []
    for line in raw.splitlines():
        devices.append(
            safe_dict(
                category="pci",
                name=line,
                source="lspci",
            )
        )
    return devices
