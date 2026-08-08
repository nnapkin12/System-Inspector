from __future__ import annotations

import psutil

from .util import run_cmd, safe_dict


def collect_network_inventory() -> list[dict]:
    items: list[dict] = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for name, addr_list in sorted(addrs.items()):
        st = stats.get(name)
        addresses = []
        for a in addr_list:
            addresses.append(
                safe_dict(
                    family=str(a.family).replace("AddressFamily.", ""),
                    address=a.address,
                    netmask=a.netmask,
                    broadcast=getattr(a, "broadcast", None),
                )
            )
        items.append(
            safe_dict(
                category="network",
                name=name,
                is_up=st.isup if st else None,
                speed_mbps=st.speed if st and st.speed > 0 else None,
                mtu=st.mtu if st else None,
                addresses=addresses,
            )
        )

    # PCI network chips for marketing names
    raw = run_cmd(["lspci", "-nn"])
    if raw:
        for line in raw.splitlines():
            low = line.lower()
            if "network controller" in low or "ethernet controller" in low:
                items.append(
                    safe_dict(
                        category="network_controller",
                        name=line.split(":", 1)[-1].strip() if ":" in line else line,
                        raw=line,
                        source="lspci",
                    )
                )
    return items


def collect_network_vitals() -> dict:
    counters = psutil.net_io_counters(pernic=False)
    per_nic = {}
    for name, c in psutil.net_io_counters(pernic=True).items():
        per_nic[name] = safe_dict(
            bytes_sent=c.bytes_sent,
            bytes_recv=c.bytes_recv,
            packets_sent=c.packets_sent,
            packets_recv=c.packets_recv,
            errin=c.errin,
            errout=c.errout,
            dropin=c.dropin,
            dropout=c.dropout,
        )
    return safe_dict(
        total=safe_dict(
            bytes_sent=counters.bytes_sent,
            bytes_recv=counters.bytes_recv,
            packets_sent=counters.packets_sent,
            packets_recv=counters.packets_recv,
        )
        if counters
        else None,
        per_nic=per_nic,
    )
