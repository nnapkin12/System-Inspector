from pathlib import Path
from unittest.mock import patch

from backend.collectors.display import collect_displays, connector_kind, parse_edid
from backend.format import fmt_hz, format_human
from backend.query import parse_query
from backend.resources import apply_fields


def _edid(
    *,
    make: str = "BOE",
    product: str = "TestPanel",
    width: int = 1920,
    height: int = 1080,
    refresh: float = 60.0,
    extra_refresh: float | None = None,
) -> bytes:
    data = bytearray(128)
    data[0:8] = bytes.fromhex("00ffffffffffff00")
    letters = [ord(c) - 64 for c in make[:3].upper()]
    raw = (letters[0] << 10) | (letters[1] << 5) | letters[2]
    data[8] = (raw >> 8) & 0xFF
    data[9] = raw & 0xFF
    data[18] = 1
    data[19] = 3

    def write_dtd(offset: int, hz: float) -> None:
        h_blank, v_blank = 280, 45
        h_total = width + h_blank
        v_total = height + v_blank
        clock = int(round(h_total * v_total * hz)) // 10_000
        data[offset] = clock & 0xFF
        data[offset + 1] = (clock >> 8) & 0xFF
        data[offset + 2] = width & 0xFF
        data[offset + 3] = h_blank & 0xFF
        data[offset + 4] = ((width >> 8) << 4) | ((h_blank >> 8) & 0x0F)
        data[offset + 5] = height & 0xFF
        data[offset + 6] = v_blank & 0xFF
        data[offset + 7] = ((height >> 8) << 4) | ((v_blank >> 8) & 0x0F)

    write_dtd(54, refresh)
    name_off = 72
    if extra_refresh is not None:
        write_dtd(72, extra_refresh)
        name_off = 90
    data[name_off + 3] = 0xFC
    text = (product[:12] + "\n").encode("ascii")
    data[name_off + 5 : name_off + 5 + len(text)] = text
    data[127] = (256 - (sum(data[:127]) % 256)) % 256
    return bytes(data)


def test_fmt_hz_integer_and_fractional():
    assert fmt_hz(144.003) == "144 Hz"
    assert fmt_hz(59.94) == "59.94 Hz"
    assert fmt_hz(None) == "—"


def test_connector_kind():
    assert connector_kind("eDP-1") == "eDP"
    assert connector_kind("HDMI-A-1") == "HDMI"
    assert connector_kind("DP-3") == "DisplayPort"


def test_parse_edid_name_and_preferred_hz():
    parsed = parse_edid(_edid(refresh=60.0, extra_refresh=144.0))
    assert parsed["make"] == "BOE"
    assert parsed["product"] == "TestPanel"
    assert parsed["width"] == 1920
    assert parsed["height"] == 1080
    assert parsed["refresh_hz"] == 60.0
    assert parsed["refresh_max_hz"] == 144.0


def test_parse_edid_rejects_short_or_bad_header():
    assert parse_edid(b"") == {}
    assert parse_edid(b"\x00" * 128) == {}


def test_collect_displays_skips_disconnected_and_writeback(tmp_path: Path):
    connected = tmp_path / "card0-eDP-1"
    connected.mkdir()
    (connected / "status").write_text("connected\n")
    (connected / "enabled").write_text("enabled\n")
    (connected / "modes").write_text("1920x1080\n1280x720\n")
    (connected / "edid").write_bytes(_edid(refresh=144.0))

    dead = tmp_path / "card0-DP-1"
    dead.mkdir()
    (dead / "status").write_text("disconnected\n")
    (dead / "edid").write_bytes(b"")

    writeback = tmp_path / "card0-Writeback-1"
    writeback.mkdir()
    (writeback / "status").write_text("unknown\n")

    with patch("backend.collectors.display.run_cmd", return_value=None):
        items = collect_displays(drm_root=tmp_path)

    assert len(items) == 1
    mon = items[0]
    assert mon["connector"] == "eDP-1"
    assert mon["kind"] == "eDP"
    assert mon["width"] == 1920
    assert mon["height"] == 1080
    assert mon["refresh_hz"] == 144.0
    assert "TestPanel" in mon["name"]
    assert mon["category"] == "display"


def test_parse_query_display_aliases():
    for word in ("display", "monitor", "monitors", "screen"):
        resources, fields, unknown = parse_query([word])
        assert resources == ["display"], word
        assert fields == set()
        assert unknown == []


def test_format_human_display():
    out = format_human(
        {
            "ok": True,
            "resource": "display",
            "data": {
                "count": 2,
                "displays": [
                    {
                        "name": "BOE panel",
                        "connector": "eDP-1",
                        "kind": "eDP",
                        "width": 1920,
                        "height": 1080,
                        "refresh_hz": 144,
                    },
                    {
                        "name": "SAM LS27DG30X",
                        "connector": "HDMI-A-1",
                        "kind": "HDMI",
                        "width": 1920,
                        "height": 1080,
                        "refresh_hz": 60,
                    },
                ],
            },
        },
        color=False,
    )
    assert "eDP-1" in out
    assert "144 Hz" in out
    assert "HDMI-A-1" in out
    assert "SAM LS27DG30X" in out


def test_format_human_display_empty():
    out = format_human(
        {"ok": True, "resource": "display", "data": {"count": 0, "displays": []}},
        color=False,
    )
    assert "none connected" in out


def test_apply_fields_display_name():
    payload = {
        "ok": True,
        "resource": "display",
        "data": {
            "displays": [
                {"name": "BOE panel", "connector": "eDP-1", "refresh_hz": 144},
            ]
        },
    }
    out = apply_fields(payload, {"name"})
    assert out["data"]["names"] == ["BOE panel"]
    assert "refresh_hz" not in out["data"]
