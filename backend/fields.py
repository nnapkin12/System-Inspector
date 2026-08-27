"""Field tokens for query parsing and formatted output."""

from __future__ import annotations

# si kernel / si os version → narrow OS block
OS_DETAIL_FIELDS = frozenset({"kernel", "hostname", "desktop", "arch", "version", "name"})

NET_FIELD_ALIASES: dict[str, str] = {
    "ip": "ip",
    "ips": "ip",
    "ipv4": "ip",
    "ipv6": "ip",
    "address": "ip",
    "addresses": "ip",
    "connections": "connections",
    "conn": "connections",
    "conns": "connections",
    "sockets": "connections",
    "listen": "listen",
    "listening": "listen",
    "ports": "listen",
    "gateway": "gateway",
    "route": "gateway",
    "default": "gateway",
    "dns": "dns",
    "nameservers": "dns",
    "resolvers": "dns",
    "routes": "routes",
    "routing": "routes",
    "wifi": "wifi",
    "wlan": "wifi",
    "wireless": "wifi",
    "public": "public",
    "publicip": "public",
    "ping": "ping",
    "latency": "ping",
    "rtt": "ping",
}

NET_DETAIL_FIELDS = frozenset(NET_FIELD_ALIASES.values())
