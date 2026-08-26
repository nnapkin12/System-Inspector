"""Connected displays via DRM sysfs + EDID (resolution, refresh Hz)."""

from __future__ import annotations

import re
from pathlib import Path

from .util import run_cmd, safe_dict

DRM = Path("/sys/class/drm")
_SKIP_CONNECTORS = ("writeback",)
_CONN_DIR = re.compile(r"^card(\d+)-(.+)$", re.IGNORECASE)


def collect_displays(*, drm_root: Path | str | None = None) -> list[dict]:
    """Connected monitors only. Writeback / disconnected connectors are skipped."""
    root = Path(drm_root) if drm_root is not None else DRM
    if not root.is_dir():
        return []

    xrandr = _xrandr_current()
    out: list[dict] = []
    for card in sorted(root.iterdir()):
        if not card.is_dir():
            continue
        parsed = _parse_connector_dir(card.name)
        if parsed is None:
            continue
        card_index, connector = parsed
        if any(s in connector.lower() for s in _SKIP_CONNECTORS):
            continue
        status = _read_text(card / "status")
        if status != "connected":
            continue
        item = _connector_item(card, card_index, connector, xrandr)
        if item:
            out.append(item)
    return out


def parse_edid(data: bytes | None) -> dict:
    """Preferred timing + product name from a raw EDID blob."""
    if not data or len(data) < 128:
        return {}
    if data[:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return {}

    make = _edid_mfg(data)
    product = None
    serial = None
    timings: list[dict] = []
    for offset in (54, 72, 90, 108):
        desc = data[offset : offset + 18]
        if len(desc) < 18:
            continue
        if desc[0] == 0 and desc[1] == 0:
            tag = desc[3]
            if tag == 0xFC:
                product = product or _edid_text(desc)
            elif tag == 0xFF:
                serial = serial or _edid_text(desc)
            continue
        timing = _edid_dtd(desc)
        if timing:
            timings.append(timing)

    preferred = timings[0] if timings else None
    max_hz = None
    if preferred and timings:
        same = [
            t["refresh_hz"]
            for t in timings
            if t.get("width") == preferred.get("width")
            and t.get("height") == preferred.get("height")
            and t.get("refresh_hz") is not None
        ]
        if same:
            max_hz = max(same)

    return safe_dict(
        make=make,
        product=product,
        serial=serial,
        width=preferred.get("width") if preferred else None,
        height=preferred.get("height") if preferred else None,
        refresh_hz=preferred.get("refresh_hz") if preferred else None,
        refresh_max_hz=max_hz if max_hz and preferred and max_hz != preferred.get("refresh_hz") else None,
    )


def connector_kind(connector: str) -> str:
    c = (connector or "").upper()
    if c.startswith("EDP"):
        return "eDP"
    if c.startswith("LVDS"):
        return "LVDS"
    if c.startswith("HDMI"):
        return "HDMI"
    if c.startswith("DP") or c.startswith("DISPLAYPORT"):
        return "DisplayPort"
    if c.startswith("DVI"):
        return "DVI"
    if c.startswith("VGA") or c.startswith("ANALOG"):
        return "VGA"
    return connector.split("-", 1)[0] if connector else "unknown"


def _connector_item(
    path: Path,
    card_index: int,
    connector: str,
    xrandr: dict[str, dict],
) -> dict:
    edid = parse_edid(_read_bytes(path / "edid"))
    width, height = _mode_wh(_read_text(path / "modes"))
    if edid.get("width"):
        width = edid["width"]
    if edid.get("height"):
        height = edid["height"]
    refresh = edid.get("refresh_hz")
    refresh_max = edid.get("refresh_max_hz")

    xr = _match_xrandr(connector, xrandr)
    if xr:
        width = xr.get("width") or width
        height = xr.get("height") or height
        if xr.get("refresh_hz") is not None:
            # Current mode from the session, when the compositor exposes it.
            if refresh is not None and xr["refresh_hz"] != refresh:
                refresh_max = refresh_max or refresh
            refresh = xr["refresh_hz"]

    kind = connector_kind(connector)
    product = edid.get("product")
    make = edid.get("make")
    if product and make:
        name = f"{make} {product}"
    elif product:
        name = product
    elif kind in ("eDP", "LVDS"):
        name = f"{make} panel" if make else "Built-in display"
    else:
        name = f"{make} display" if make else connector

    enabled_raw = _read_text(path / "enabled")
    return safe_dict(
        category="display",
        name=name,
        connector=connector,
        kind=kind,
        card=card_index,
        status="connected",
        enabled=enabled_raw == "enabled" if enabled_raw else None,
        width=width,
        height=height,
        refresh_hz=refresh,
        refresh_max_hz=refresh_max if refresh_max and refresh_max != refresh else None,
        make=make,
        product=product,
        serial=edid.get("serial"),
        source="drm",
    )


def _parse_connector_dir(name: str) -> tuple[int, str] | None:
    m = _CONN_DIR.fullmatch(name)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def _mode_wh(modes: str | None) -> tuple[int | None, int | None]:
    if not modes:
        return None, None
    for line in modes.splitlines():
        m = re.match(r"^\s*(\d+)x(\d+)", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def _edid_mfg(data: bytes) -> str | None:
    raw = (data[8] << 8) | data[9]
    chars: list[str] = []
    for shift in (10, 5, 0):
        n = (raw >> shift) & 0x1F
        if not n:
            return None
        chars.append(chr(n + 64))
    return "".join(chars)


def _edid_text(desc: bytes) -> str | None:
    raw = bytes(desc[5:18]).split(b"\n", 1)[0]
    text = raw.decode("ascii", errors="ignore").strip().strip("\x00")
    return text or None


def _edid_dtd(desc: bytes) -> dict | None:
    clock = (desc[0] | (desc[1] << 8)) * 10_000
    if clock <= 0:
        return None
    h_active = desc[2] | ((desc[4] >> 4) << 8)
    h_blank = desc[3] | ((desc[4] & 0x0F) << 8)
    v_active = desc[5] | ((desc[7] >> 4) << 8)
    v_blank = desc[6] | ((desc[7] & 0x0F) << 8)
    h_total = h_active + h_blank
    v_total = v_active + v_blank
    if not h_active or not v_active or not h_total or not v_total:
        return None
    refresh = _clean_hz(clock / (h_total * v_total))
    return safe_dict(width=h_active, height=v_active, refresh_hz=refresh)


def _clean_hz(value: float) -> float:
    rounded = round(float(value), 2)
    nearest = float(round(rounded))
    if abs(rounded - nearest) < 0.05:
        return nearest
    return rounded


def _xrandr_current() -> dict[str, dict]:
    raw = run_cmd(["xrandr", "--query"])
    if not raw:
        return {}
    out: dict[str, dict] = {}
    current_name: str | None = None
    header = re.compile(
        r"^(\S+)\s+connected(?:\s+primary)?(?:\s+(\d+)x(\d+))?",
        re.IGNORECASE,
    )
    mode = re.compile(r"^\s+(\d+)x(\d+)\s+(.+)$")
    for line in raw.splitlines():
        hm = header.match(line)
        if hm:
            current_name = hm.group(1)
            item: dict = {}
            if hm.group(2):
                item["width"] = int(hm.group(2))
                item["height"] = int(hm.group(3))
            out[current_name] = item
            continue
        if current_name is None:
            continue
        mm = mode.match(line)
        if not mm:
            if line and not line.startswith(" "):
                current_name = None
            continue
        rates = mm.group(3)
        if "*" not in rates:
            continue
        token = next((t for t in rates.split() if "*" in t), None)
        if not token:
            continue
        hz_s = token.replace("*", "").replace("+", "")
        try:
            hz = _clean_hz(float(hz_s))
        except ValueError:
            continue
        item = out.setdefault(current_name, {})
        item["width"] = int(mm.group(1))
        item["height"] = int(mm.group(2))
        item["refresh_hz"] = hz
    return out


def _match_xrandr(connector: str, xrandr: dict[str, dict]) -> dict:
    for key in _connector_aliases(connector):
        if key in xrandr:
            return xrandr[key]
    return {}


def _connector_aliases(connector: str) -> list[str]:
    names = [connector]
    m = re.fullmatch(r"(HDMI)-A-(\d+)", connector, re.IGNORECASE)
    if m:
        names.append(f"{m.group(1)}-{m.group(2)}")
    m = re.fullmatch(r"(HDMI)-(\d+)", connector, re.IGNORECASE)
    if m:
        names.append(f"{m.group(1)}-A-{m.group(2)}")
    return names


def _read_text(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def _read_bytes(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None
