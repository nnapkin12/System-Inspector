from __future__ import annotations

import re
import socket
import struct
import time
from typing import Any

import psutil

from .util import read_text, run_cmd, safe_dict

_CONN_LIMIT = 80
_LISTEN_LIMIT = 60


def _family_label(family: Any) -> str:
    return str(family).replace("AddressFamily.", "")


def _proc_name(pid: int | None) -> str | None:
    if pid is None or pid < 0:
        return None
    try:
        return psutil.Process(pid).name()
    except (psutil.Error, OSError):
        return None


def _socket_type_label(kind: Any) -> str | None:
    if kind is None:
        return None
    name = str(kind).replace("SocketKind.", "")
    mapping = {
        "SOCK_STREAM": "TCP",
        "SOCK_DGRAM": "UDP",
        "1": "TCP",
        "2": "UDP",
    }
    return mapping.get(name, name)


def _format_addr(addr: tuple | None) -> str | None:
    if not addr:
        return None
    host, port = addr
    if not host:
        host = "*"
    if port is None:
        return str(host)
    return f"{host}:{port}"


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
                    family=_family_label(a.family),
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


def _is_ip_family(family: Any, *, ipv6: bool = False) -> bool:
    want = socket.AF_INET6 if ipv6 else socket.AF_INET
    if family == want:
        return True
    label = _family_label(family)
    if ipv6:
        return "INET6" in label or "IPV6" in label
    return "INET" in label and "INET6" not in label


def collect_ip_addresses(include_loopback: bool = False) -> list[dict]:
    rows: list[dict] = []
    for name, addr_list in sorted(psutil.net_if_addrs().items()):
        if name == "lo" and not include_loopback:
            continue
        for a in addr_list:
            if _is_ip_family(a.family, ipv6=False):
                fam = "ipv4"
            elif _is_ip_family(a.family, ipv6=True):
                fam = "ipv6"
            else:
                continue
            if not include_loopback and a.address.startswith("127."):
                continue
            if not include_loopback and a.address == "::1":
                continue
            rows.append(
                safe_dict(
                    interface=name,
                    family=fam,
                    address=a.address,
                    netmask=a.netmask,
                )
            )
    return rows


def _proc_stats(pid: int | None) -> tuple[float | None, float | None]:
    if pid is None or pid < 0:
        return None, None
    try:
        proc = psutil.Process(pid)
        cpu = proc.cpu_percent(interval=0.0)
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
        return cpu, mem_mb
    except (psutil.Error, OSError):
        return None, None


def _prime_proc_cpu(pids: set[int]) -> None:
    for pid in pids:
        try:
            psutil.Process(pid).cpu_percent(interval=0.0)
        except (psutil.Error, OSError):
            continue
    if pids:
        time.sleep(0.05)


_PORT_NAMES = {"http": "80", "https": "443", "ssh": "22", "domain": "53"}


def _normalize_hostport(addr: str | None) -> str | None:
    if not addr:
        return None
    if addr.count(":") > 1 and not addr.startswith("["):
        # IPv6 without brackets host:port from the end
        host, port = addr.rsplit(":", 1)
    elif addr.startswith("[") and "]:" in addr:
        host, port = addr.split("]:", 1)
        host = host + "]"
    elif ":" in addr:
        host, port = addr.rsplit(":", 1)
    else:
        return addr
    port = _PORT_NAMES.get(port.lower(), port)
    return f"{host}:{port}"


def _conn_key(local: str | None, remote: str | None) -> str | None:
    if not local or not remote:
        return None
    return f"{_normalize_hostport(local)}->{_normalize_hostport(remote)}"


def _ss_rtt_map() -> dict[str, float]:
    """Map 'local->remote' keys to smoothed RTT in ms from ss."""
    raw = run_cmd(["ss", "-H", "-ti", "state", "established"], timeout=3.0)
    if not raw:
        return {}

    out: dict[str, float] = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        parts = line.split()
        if len(parts) >= 4 and parts[0].isdigit():
            local, remote = parts[2], parts[3]
            rtt_ms = None
            if i + 1 < len(lines):
                m = re.search(r"rtt:([\d.]+)/", lines[i + 1], flags=re.I)
                if m:
                    rtt_ms = round(float(m.group(1)), 1)
            key = _conn_key(local, remote)
            if key and rtt_ms is not None:
                out[key] = rtt_ms
            i += 2
            continue
        i += 1
    return out


def _connection_health(cpu: float | None, status: str | None, rtt_ms: float | None) -> str:
    levels: list[int] = []

    if cpu is not None:
        if cpu >= 40:
            levels.append(2)
        elif cpu >= 10:
            levels.append(1)
        else:
            levels.append(0)

    if status:
        s = str(status).upper()
        if s in {"CLOSE_WAIT", "CLOSING", "LAST_ACK", "FIN_WAIT1", "FIN_WAIT2"}:
            levels.append(2)
        elif s in {"SYN_SENT", "SYN_RECV", "TIME_WAIT"}:
            levels.append(1)
        elif s == "ESTABLISHED":
            levels.append(0)

    if rtt_ms is not None:
        if rtt_ms >= 200:
            levels.append(2)
        elif rtt_ms >= 80:
            levels.append(1)
        else:
            levels.append(0)

    if not levels:
        return "unknown"
    return ("good", "warn", "bad")[max(levels)]


def _listener_health(address: str | None, process: str | None) -> str:
    addr = address or ""
    host = addr.rsplit(":", 1)[0] if ":" in addr else addr
    if host in {"127.0.0.1", "::1", "[::1]"}:
        base = "good"
    elif host in {"0.0.0.0", "*", "::", "[::]"}:
        base = "warn"
    else:
        base = "good"
    if not process or process == "?":
        return "warn" if base == "good" else "bad"
    return base


def collect_connections(limit: int | None = _CONN_LIMIT) -> dict:
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.Error, PermissionError, OSError) as exc:
        return {
            "available": False,
            "connections": [],
            "total": 0,
            "shown": 0,
            "note": f"Could not read connections ({exc}). Try running with sudo for a full view.",
        }

    pid_cache: dict[int, str | None] = {}
    pid_set: set[int] = set()
    rows: list[dict] = []
    for c in conns:
        if c.status == psutil.CONN_LISTEN:
            continue
        pid = c.pid
        if pid not in pid_cache:
            pid_cache[pid] = _proc_name(pid)
        if pid is not None and pid >= 0:
            pid_set.add(pid)

    _prime_proc_cpu(pid_set)
    rtt_map = _ss_rtt_map()

    for c in conns:
        if c.status == psutil.CONN_LISTEN:
            continue
        pid = c.pid
        cpu, mem_mb = _proc_stats(pid)
        local = _format_addr(c.laddr)
        remote = _format_addr(c.raddr)
        rtt_ms = rtt_map.get(_conn_key(local, remote) or "")
        status = c.status
        health = _connection_health(cpu, status, rtt_ms)
        rows.append(
            safe_dict(
                family=_family_label(c.family) if c.family else None,
                type=_socket_type_label(c.type),
                local=local,
                remote=remote,
                status=status,
                pid=pid,
                process=pid_cache.get(pid),
                process_cpu=round(cpu, 1) if cpu is not None else None,
                process_mem_mb=mem_mb,
                rtt_ms=rtt_ms,
                health=health,
            )
        )

    rows.sort(key=lambda r: (r.get("status") or "", r.get("process") or "", r.get("remote") or ""))
    total = len(rows)
    note = None
    if limit is not None and total > limit:
        note = f"Showing {limit} of {total} active connections (non-listening)."
        rows = rows[:limit]
    elif not rows:
        note = "No active outbound/inbound connections (excluding listeners)."

    return safe_dict(
        available=True,
        connections=rows,
        total=total,
        shown=len(rows),
        note=note,
    )


def collect_listeners(limit: int = _LISTEN_LIMIT) -> dict:
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.Error, PermissionError, OSError) as exc:
        return {
            "available": False,
            "listeners": [],
            "total": 0,
            "shown": 0,
            "note": f"Could not read listening ports ({exc}). Try running with sudo for a full view.",
        }

    pid_cache: dict[int, str | None] = {}
    rows: list[dict] = []
    for c in conns:
        if c.status != psutil.CONN_LISTEN:
            continue
        pid = c.pid
        if pid not in pid_cache:
            pid_cache[pid] = _proc_name(pid)
        rows.append(
            safe_dict(
                family=_family_label(c.family) if c.family else None,
                address=_format_addr(c.laddr),
                pid=pid,
                process=pid_cache.get(pid),
                health=_listener_health(_format_addr(c.laddr), pid_cache.get(pid)),
            )
        )

    rows.sort(key=lambda r: (r.get("process") or "", r.get("address") or ""))
    total = len(rows)
    note = None
    if total > limit:
        note = f"Showing {limit} of {total} listening sockets."
        rows = rows[:limit]
    elif not rows:
        note = "No listening sockets reported."

    return safe_dict(
        available=True,
        listeners=rows,
        total=total,
        shown=len(rows),
        note=note,
    )


def _gateway_from_proc() -> str | None:
    data = read_text("/proc/net/route")
    if not data:
        return None
    for line in data.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        dest, gateway, flags = parts[1], parts[2], parts[3] if len(parts) > 3 else "0"
        if dest != "00000000":
            continue
        try:
            flag_val = int(flags, 16)
        except ValueError:
            continue
        if not (flag_val & 2):  # RTF_GATEWAY
            continue
        if gateway == "00000000":
            continue
        gw = socket.inet_ntoa(struct.pack("<L", int(gateway, 16)))
        return gw
    return None


def collect_gateway() -> dict:
    gateway = _gateway_from_proc()
    iface = None
    raw = run_cmd(["ip", "route", "show", "default"], timeout=2.0)
    if raw:
        parts = raw.split()
        if "dev" in parts:
            iface = parts[parts.index("dev") + 1]
        if not gateway and len(parts) >= 3:
            gateway = parts[2] if parts[0] == "default" else gateway
    if not gateway:
        raw2 = run_cmd(["route", "-n"], timeout=2.0)
        if raw2:
            for line in raw2.splitlines()[2:]:
                cols = line.split()
                if len(cols) >= 8 and cols[0] in ("0.0.0.0", "default"):
                    gateway = cols[1]
                    iface = cols[-1]
                    break
    return safe_dict(
        gateway=gateway,
        interface=iface,
        note=None if gateway else "Default gateway not found.",
    )


def collect_dns() -> dict:
    servers: list[str] = []
    resolv = read_text("/etc/resolv.conf")
    if resolv:
        for line in resolv.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    servers.append(parts[1])

    source = "resolv.conf" if servers else None
    nm = run_cmd(["nmcli", "-t", "-f", "IP4.DNS", "dev", "show"], timeout=2.0)
    if nm:
        for line in nm.splitlines():
            for chunk in line.split(":"):
                chunk = chunk.strip()
                if not chunk or chunk.startswith("IP"):
                    continue
                if chunk not in servers:
                    servers.append(chunk)
        if servers:
            source = "NetworkManager"

    return safe_dict(
        servers=servers,
        source=source,
        note=None if servers else "No DNS servers found in resolv.conf or NetworkManager.",
    )


def collect_routes() -> dict:
    rows: list[dict] = []
    raw = run_cmd(["ip", "route"], timeout=2.0)
    if raw:
        for line in raw.splitlines():
            if not line.strip():
                continue
            rows.append(safe_dict(route=line.strip(), source="ip"))
        return safe_dict(routes=rows, source="ip")

    raw = run_cmd(["route", "-n"], timeout=2.0)
    if raw:
        for line in raw.splitlines()[2:]:
            cols = line.split()
            if len(cols) >= 8:
                rows.append(
                    safe_dict(
                        destination=cols[0],
                        gateway=cols[1],
                        netmask=cols[2],
                        flags=cols[3],
                        interface=cols[-1],
                        source="route",
                    )
                )
        return safe_dict(routes=rows, source="route")

    return safe_dict(routes=[], note="Routing table unavailable (ip/route not found).")


def collect_wifi() -> dict:
    nm = run_cmd(
        ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi"],
        timeout=2.0,
    )
    if nm:
        active = None
        networks: list[dict] = []
        for line in nm.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            entry = safe_dict(
                active=parts[0] == "yes",
                ssid=parts[1] or None,
                signal=int(parts[2]) if parts[2].isdigit() else None,
                security=parts[3] or None,
            )
            networks.append(entry)
            if entry.get("active"):
                active = entry
        if networks:
            return safe_dict(
                available=True,
                active=active,
                networks=networks[:20],
                source="nmcli",
            )

    iw = run_cmd(["iwgetid", "-r"], timeout=2.0)
    if iw:
        return safe_dict(
            available=True,
            active=safe_dict(ssid=iw, active=True),
            source="iwgetid",
        )

    return safe_dict(
        available=False,
        note="WiFi info not available (install NetworkManager/nmcli or connect via WiFi).",
    )


def collect_public_ip() -> dict:
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
    ):
        raw = run_cmd(["curl", "-fsS", "--max-time", "3", url], timeout=4.0)
        if raw:
            ip = raw.splitlines()[0].strip()
            if ip:
                return safe_dict(
                    address=ip,
                    source=url,
                    requires_network=True,
                )
    return safe_dict(
        address=None,
        requires_network=True,
        note="Could not reach a public IP service (needs internet).",
    )
