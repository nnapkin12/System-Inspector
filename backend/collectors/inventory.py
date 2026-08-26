from __future__ import annotations

from datetime import datetime, timezone

from .cpu import collect_cpu_inventory
from .display import collect_displays
from .gpu import collect_gpus_inventory
from .memory import collect_memory_inventory
from .motherboard import collect_board, collect_pci_devices
from .network import collect_network_inventory
from .os_info import collect_os
from .storage import collect_storage_inventory
from .util import safe_dict


def get_inventory(include_pci: bool = True) -> dict:
    """Full static-ish hardware/OS inventory as clean JSON-ready dict."""
    components: list[dict] = []

    os_info = collect_os()
    cpu = collect_cpu_inventory()
    gpus = collect_gpus_inventory()
    displays = collect_displays()
    memory = collect_memory_inventory()
    storage = collect_storage_inventory()
    network = collect_network_inventory()
    board = collect_board()

    components.append(os_info)
    components.append(cpu)
    components.extend(gpus)
    components.extend(displays)
    components.extend(memory)
    components.extend(storage)
    components.extend(network)
    components.extend(board)

    if include_pci:
        components.extend(collect_pci_devices())

    summary = {
        "os": os_info.get("name"),
        "cpu": cpu.get("name"),
        "gpus": [g.get("name") for g in gpus if g.get("name")],
        "ram_gb": next((m.get("total_gb") for m in memory if m.get("category") == "memory"), None),
        "hostname": os_info.get("hostname"),
        "uptime_seconds": os_info.get("uptime_seconds"),
        "desktop": os_info.get("desktop_environment"),
    }

    return safe_dict(
        collected_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
        components=components,
        counts={
            "total_components": len(components),
            "gpus": len(gpus),
            "displays": len(displays),
            "storage_entries": len(storage),
            "network_entries": len(network),
        },
    )
