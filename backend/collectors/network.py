from __future__ import annotations

import re
import socket
import struct
import time
from pathlib import Path
from typing import Any

import psutil

from .util import read_text, run_cmd, safe_dict


_SKIP_NIC_PREFIXES = ("docker", "br-", "veth", "virbr", "vmnet")


def keep_nic(name: str) -> bool:
    """Real-ish NICs for per-interface rates (hide docker/bridge spam)."""
    low = (name or "").lower()
    if not low or low == "lo" or low.startswith("lo:"):
        return False
    return not any(low.startswith(p) for p in _SKIP_NIC_PREFIXES)


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


def collect_connections(limit: int | None = None) -> dict:
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


def collect_listeners(limit: int | None = None) -> dict:
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
    if limit is not None and total > limit:
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
    fields = "ACTIVE,SSID,CHAN,FREQ,SIGNAL,RATE,SECURITY"
    nm = run_cmd(
        ["nmcli", "-t", "-f", fields, "dev", "wifi", "list", "--rescan", "no"],
        timeout=3.0,
    )
    if not nm:
        nm = run_cmd(
            ["nmcli", "-t", "-f", fields, "dev", "wifi", "list", "--rescan", "yes"],
            timeout=12.0,
        )
    if not nm:
        nm = run_cmd(
            ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "no"],
            timeout=3.0,
        )
    networks: list[dict] = []
    if nm:
        for line in nm.splitlines():
            entry = _parse_nmcli_wifi_row(line)
            if entry:
                networks.append(entry)

    link = _wifi_link_info()
    active = next((n for n in networks if n.get("active")), None)
    if active and link:
        for key in ("signal_dbm", "freq_mhz", "channel", "bitrate", "ssid"):
            if link.get(key) is not None and active.get(key) is None:
                active[key] = link[key]
        if link.get("ssid") and not active.get("ssid"):
            active["ssid"] = link["ssid"]
    elif link and not active:
        active = safe_dict(active=True, **link)
        networks.insert(0, dict(active))

    if networks or active:
        channels = wifi_channel_counts(networks)
        yours = (active or {}).get("channel")
        on_yours = channels.get(yours, 0) if yours is not None else 0
        return safe_dict(
            available=True,
            active=active,
            networks=networks,
            channels=[{"channel": ch, "count": n} for ch, n in sorted(channels.items())],
            yours_channel=yours,
            aps_on_channel=on_yours or None,
            source="nmcli" if nm else "iw",
        )

    iw = run_cmd(["iwgetid", "-r"], timeout=2.0)
    if iw:
        return safe_dict(
            available=True,
            active=safe_dict(ssid=iw, active=True, **(link or {})),
            source="iwgetid",
        )

    return safe_dict(
        available=False,
        note="WiFi info not available (install NetworkManager/nmcli or connect via WiFi).",
    )


def _parse_nmcli_wifi_row(line: str) -> dict | None:
    parts = split_nmcli_line(line)
    if len(parts) < 4:
        return None
    # ACTIVE,SSID,SIGNAL,SECURITY  or  ACTIVE,SSID,CHAN,FREQ,SIGNAL,RATE,SECURITY
    active = parts[0] == "yes"
    ssid = parts[1] or None
    if len(parts) >= 7:
        chan_s, freq_s, sig_s, rate, security = parts[2], parts[3], parts[4], parts[5], parts[6]
    else:
        chan_s, freq_s, rate = "", "", None
        sig_s, security = parts[2], parts[3]
    return safe_dict(
        active=active,
        ssid=ssid,
        channel=_int_or_none(chan_s),
        freq_mhz=_freq_mhz(freq_s),
        signal=_int_or_none(sig_s),
        bitrate=rate or None,
        security=security or None,
    )


def split_nmcli_line(line: str) -> list[str]:
    """Split nmcli -t output; `\\:` is a literal colon (SSIDs, etc.)."""
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if line[i] == ":":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(line[i])
        i += 1
    parts.append("".join(buf))
    return parts


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text.split()[0]))
    except (TypeError, ValueError):
        return None


def _freq_mhz(value: str | None) -> int | None:
    n = _int_or_none(value)
    if n is None:
        return None
    # nmcli sometimes reports Hz
    if n > 100_000:
        n = int(round(n / 1_000_000))
    return n


def wifi_channel_counts(networks: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for row in networks:
        ch = row.get("channel")
        if ch is None:
            continue
        try:
            key = int(ch)
        except (TypeError, ValueError):
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def wifi_band(freq_mhz: int | None) -> str | None:
    if freq_mhz is None:
        return None
    if 2400 <= freq_mhz < 2500:
        return "2.4 GHz"
    if 4900 <= freq_mhz < 5900:
        return "5 GHz"
    if 5900 <= freq_mhz < 7200:
        return "6 GHz"
    return None


def _wifi_ifaces() -> list[str]:
    root = Path("/sys/class/net")
    if not root.is_dir():
        return []
    names: list[str] = []
    for entry in sorted(root.iterdir()):
        if (entry / "wireless").exists() or (entry / "phy80211").exists():
            names.append(entry.name)
    return names


def _wifi_link_info() -> dict:
    for iface in _wifi_ifaces():
        raw = run_cmd(["iw", "dev", iface, "link"], timeout=2.0)
        if not raw or "Not connected" in raw:
            continue
        parsed = parse_iw_link(raw)
        if parsed:
            parsed["interface"] = iface
            return parsed
    return {}


def parse_iw_link(raw: str) -> dict:
    ssid = None
    signal_dbm = None
    freq_mhz = None
    bitrate = None
    for line in raw.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("ssid:"):
            ssid = s.split(":", 1)[1].strip() or None
        elif "signal:" in low:
            m = re.search(r"(-\d+(?:\.\d+)?)\s*dBm", s, flags=re.I)
            if m:
                signal_dbm = round(float(m.group(1)), 1)
        elif low.startswith("freq:"):
            freq_mhz = _int_or_none(s.split(":", 1)[1])
        elif "tx bitrate:" in low or low.startswith("tx bitrate"):
            bitrate = s.split(":", 1)[-1].strip() or None
    channel = _channel_from_freq(freq_mhz)
    return safe_dict(
        ssid=ssid,
        signal_dbm=signal_dbm,
        freq_mhz=freq_mhz,
        channel=channel,
        bitrate=bitrate,
    )


def _channel_from_freq(freq_mhz: int | None) -> int | None:
    if freq_mhz is None:
        return None
    # Common 2.4 GHz: 2412 + 5*(ch-1)
    if 2412 <= freq_mhz <= 2484:
        if freq_mhz == 2484:
            return 14
        return 1 + (freq_mhz - 2412) // 5
    return None


def parse_ping_output(raw: str) -> dict:
    """Parse Linux/iputils ping -c N stdout."""
    sent = recv = loss_pct = None
    m = re.search(
        r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets\s+)?received.*?(\d+(?:\.\d+)?)%\s+packet loss",
        raw,
        flags=re.I | re.S,
    )
    if m:
        sent, recv, loss_pct = int(m.group(1)), int(m.group(2)), float(m.group(3))
    rtt_min = rtt_avg = rtt_max = None
    r = re.search(
        r"(?:rtt|round-trip)\s+min/avg/max(?:/mdev)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)",
        raw,
        flags=re.I,
    )
    if r:
        rtt_min, rtt_avg, rtt_max = (round(float(x), 2) for x in r.groups())
    health = "unknown"
    if loss_pct is not None:
        if loss_pct >= 50 or (recv is not None and recv == 0):
            health = "bad"
        elif loss_pct > 0 or (rtt_avg is not None and rtt_avg >= 80):
            health = "warn"
        else:
            health = "good"
    return safe_dict(
        packets_sent=sent,
        packets_recv=recv,
        loss_percent=loss_pct,
        rtt_min_ms=rtt_min,
        rtt_avg_ms=rtt_avg,
        rtt_max_ms=rtt_max,
        health=health,
    )


def collect_gateway_ping() -> dict:
    """ICMP to the default gateway only — LAN check, not a speedtest."""
    gw = collect_gateway()
    target = gw.get("gateway")
    if not target:
        return safe_dict(
            available=False,
            gateway=gw,
            note=gw.get("note") or "No default gateway to ping.",
        )
    raw = run_cmd(
        ["ping", "-c", "3", "-n", "-W", "1", str(target)],
        timeout=6.0,
        ok_returncodes=(0, 1, 2),
    )
    if not raw:
        return safe_dict(
            available=False,
            target=target,
            gateway=gw,
            note="ping failed (missing ping, blocked ICMP, or timed out).",
        )
    stats = parse_ping_output(raw)
    return safe_dict(
        available=True,
        target=target,
        interface=gw.get("interface"),
        **stats,
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


NET_STATIC_TTL = 30.0
_net_static_cache: dict | None = None
_net_static_at: float = 0.0


def collect_net_static(*, ttl: float = NET_STATIC_TTL) -> dict:
    """Gateway, DNS, and addresses — cached for live `si net` ticks."""
    global _net_static_cache, _net_static_at
    now = time.monotonic()
    if _net_static_cache is not None and (now - _net_static_at) < ttl:
        return _net_static_cache
    data = {
        "addresses": collect_ip_addresses(),
        "gateway": collect_gateway(),
        "dns": collect_dns(),
    }
    _net_static_cache = data
    _net_static_at = now
    return data


def reset_net_static_cache_for_tests() -> None:
    global _net_static_cache, _net_static_at
    _net_static_cache = None
    _net_static_at = 0.0
