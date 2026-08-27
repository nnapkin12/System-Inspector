from backend.collectors.network import (
    keep_nic,
    parse_iw_link,
    parse_ping_output,
    split_nmcli_line,
    wifi_band,
    wifi_channel_counts,
)
from backend.format import format_human
from backend.live_mode import query_is_liveable
from backend.query import parse_query


def test_split_nmcli_escapes_colons():
    parts = split_nmcli_line(r"yes:Foo\:Bar:6:2437 MHz:72:130 Mbit/s:WPA2")
    assert parts[0] == "yes"
    assert parts[1] == "Foo:Bar"
    assert parts[2] == "6"
    assert parts[4] == "72"


def test_wifi_channel_counts_and_band():
    nets = [
        {"channel": 6, "ssid": "a"},
        {"channel": 6, "ssid": "b"},
        {"channel": 1, "ssid": "c"},
        {"ssid": "hidden"},
    ]
    assert wifi_channel_counts(nets) == {6: 2, 1: 1}
    assert wifi_band(2437) == "2.4 GHz"
    assert wifi_band(5180) == "5 GHz"


def test_parse_iw_link_dbm():
    raw = """
Connected to aa:bb:cc:dd:ee:ff (on wlo1)
	SSID: HomeNet
	freq: 5220
	signal: -52 dBm
	tx bitrate: 433.3 MBit/s
"""
    out = parse_iw_link(raw)
    assert out["ssid"] == "HomeNet"
    assert out["signal_dbm"] == -52.0
    assert out["freq_mhz"] == 5220
    assert "433" in (out.get("bitrate") or "")


def test_parse_ping_output_ok():
    raw = """
PING 192.168.0.1 (192.168.0.1) 56(84) bytes of data.
64 bytes from 192.168.0.1: icmp_seq=1 ttl=64 time=1.23 ms

--- 192.168.0.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2003ms
rtt min/avg/max/mdev = 1.10/1.50/2.20/0.40 ms
"""
    out = parse_ping_output(raw)
    assert out["packets_sent"] == 3
    assert out["packets_recv"] == 3
    assert out["loss_percent"] == 0.0
    assert out["rtt_avg_ms"] == 1.5
    assert out["health"] == "good"


def test_parse_ping_output_loss_is_bad():
    raw = """
3 packets transmitted, 0 received, 100% packet loss, time 2040ms
"""
    out = parse_ping_output(raw)
    assert out["loss_percent"] == 100.0
    assert out["health"] == "bad"


def test_keep_nic_hides_virtual():
    assert keep_nic("wlo1") is True
    assert keep_nic("enp4s0") is True
    assert keep_nic("lo") is False
    assert keep_nic("docker0") is False
    assert keep_nic("veth1234") is False
    assert keep_nic("br-abc") is False
    assert keep_nic("wg0") is True


def test_parse_ping_is_net_slice():
    resources, fields, unknown = parse_query(["ping"])
    assert resources == ["net"]
    assert fields == {"ping"}
    assert unknown == []
    resources, fields, unknown = parse_query(["net", "latency"])
    assert resources == ["net"]
    assert fields == {"ping"}


def test_ping_and_wifi_are_snapshots():
    assert query_is_liveable(["net", "ping"]) is False
    assert query_is_liveable(["ping"]) is False
    assert query_is_liveable(["net", "wifi"]) is False
    assert query_is_liveable(["net"]) is True


def test_format_wifi_channel_and_dbm():
    out = format_human(
        {
            "ok": True,
            "resource": "net",
            "fields": ["wifi"],
            "data": {
                "wifi": {
                    "available": True,
                    "aps_on_channel": 5,
                    "active": {
                        "ssid": "HomeNet",
                        "signal": 72,
                        "signal_dbm": -52,
                        "channel": 6,
                        "freq_mhz": 2437,
                        "security": "WPA2",
                    },
                    "networks": [
                        {"active": True, "ssid": "HomeNet", "channel": 6},
                        {"active": False, "ssid": "Other", "signal": 40, "channel": 1},
                    ],
                }
            },
        },
        color=False,
    )
    assert "HomeNet" in out
    assert "-52 dBm" in out
    assert "ch 6" in out
    assert "busy" in out
    assert "Other" in out


def test_format_ping():
    out = format_human(
        {
            "ok": True,
            "resource": "net",
            "fields": ["ping"],
            "data": {
                "ping": {
                    "available": True,
                    "target": "192.168.0.1",
                    "interface": "wlo1",
                    "loss_percent": 0,
                    "rtt_avg_ms": 1.4,
                    "health": "good",
                }
            },
        },
        color=False,
    )
    assert "192.168.0.1" in out
    assert "1.4 ms" in out
    assert "0% loss" in out


def test_format_net_per_nic_when_several():
    out = format_human(
        {
            "ok": True,
            "resource": "net",
            "data": {
                "rates_mbs": {
                    "recv": 0.2,
                    "sent": 0.1,
                    "per_nic": [
                        {"name": "wlo1", "recv": 0.2, "sent": 0.1},
                        {"name": "enp4s0", "recv": 0.0, "sent": 0.0},
                    ],
                },
                "gateway": {},
                "dns": {},
                "addresses": [],
            },
        },
        color=False,
    )
    assert "wlo1" in out
    assert "enp4s0" in out
