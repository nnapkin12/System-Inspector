"""Strip or mask identifiers before printing or piping JSON."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Keys matched case-insensitively at any depth
_SENSITIVE_KEYS = frozenset(
    {
        "serial",
        "uuid",
        "boot_id",
        "raw_os_release",
        "part_number",
        "sku",
        "asset_tag",
    }
)


def _mask(value: str) -> str:
    text = str(value).strip()
    if not text:
        return text
    if len(text) <= 4:
        return "****"
    return f"****{text[-4:]}"


def _walk(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if key.lower() in _SENSITIVE_KEYS:
                if key.lower() == "raw_os_release":
                    out[key] = {"redacted": True}
                elif val is None:
                    out[key] = None
                elif isinstance(val, str):
                    out[key] = _mask(val)
                else:
                    out[key] = "[redacted]"
            else:
                out[key] = _walk(val)
        return out
    if isinstance(obj, list):
        return [_walk(item) for item in obj]
    return obj


def redact_payload(payload: dict) -> dict:
    """Return a copy with serials, UUIDs, boot_id, sku, asset tags, and raw os-release masked."""
    return _walk(deepcopy(payload))
