from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .cpu import collect_cpu_vitals
from .gpu import collect_gpus_vitals
from .memory import collect_memory_vitals
from .network import collect_network_vitals
from .storage import collect_storage_vitals
from .util import read_text, safe_dict

# Prime cpu_percent so first real poll is meaningful
psutil.cpu_percent(interval=None)

_rate_lock = threading.Lock()
_prev_io: dict | None = None
_last_rates: dict = {
    "disk_read_mbs": 0.0,
    "disk_write_mbs": 0.0,
    "net_recv_mbs": 0.0,
    "net_sent_mbs": 0.0,
    "ready": False,
}


def _disk_counters() -> tuple[int, int]:
    """Total disk bytes, favoring real block devices over loops."""
    per = psutil.disk_io_counters(perdisk=True) or {}
    read = write = 0
    any_real = False
    for name, c in per.items():
        low = name.lower()
        if low.startswith(("loop", "ram", "dm-", "zram", "sr")):
            continue
        any_real = True
        read += c.read_bytes
        write += c.write_bytes
    if any_real:
        return read, write
    total = psutil.disk_io_counters(perdisk=False)
    if not total:
        return 0, 0
    return total.read_bytes, total.write_bytes


def _net_counters() -> tuple[int, int]:
    """Network bytes excluding loopback."""
    per = psutil.net_io_counters(pernic=True) or {}
    recv = sent = 0
    for name, c in per.items():
        if name == "lo" or name.startswith("lo:"):
            continue
        recv += c.bytes_recv
        sent += c.bytes_sent
    if recv or sent:
        return recv, sent
    total = psutil.net_io_counters(pernic=False)
    if not total:
        return 0, 0
    return total.bytes_recv, total.bytes_sent


def _sample_io() -> dict:
    now = time.monotonic()
    dr, dw = _disk_counters()
    nr, ns = _net_counters()
    return {
        "t": now,
        "disk_read": dr,
        "disk_write": dw,
        "net_recv": nr,
        "net_sent": ns,
    }


def _update_rates_from_sample(sample: dict) -> dict:
    global _prev_io
    with _rate_lock:
        rates = {
            "disk_read_mbs": _last_rates.get("disk_read_mbs", 0.0),
            "disk_write_mbs": _last_rates.get("disk_write_mbs", 0.0),
            "net_recv_mbs": _last_rates.get("net_recv_mbs", 0.0),
            "net_sent_mbs": _last_rates.get("net_sent_mbs", 0.0),
            "ready": _last_rates.get("ready", False),
        }
        if _prev_io is not None:
            dt = max(sample["t"] - _prev_io["t"], 0.05)

            def mbs(cur: float, prev: float) -> float:
                return round(max(cur - prev, 0.0) / dt / (1024 * 1024), 3)

            rates = {
                "disk_read_mbs": mbs(sample["disk_read"], _prev_io["disk_read"]),
                "disk_write_mbs": mbs(sample["disk_write"], _prev_io["disk_write"]),
                "net_recv_mbs": mbs(sample["net_recv"], _prev_io["net_recv"]),
                "net_sent_mbs": mbs(sample["net_sent"], _prev_io["net_sent"]),
                "ready": True,
            }
            _last_rates.update(rates)
        _prev_io = sample
        return dict(rates)


def _throughput() -> dict:
    """Disk + network rates (MB/s). Always returns numbers after first interval."""
    return _update_rates_from_sample(_sample_io())


def collect_fans() -> list[dict]:
    """
    Fan sensors. Many laptops (including HP ACPI) expose fan nodes that
    permanently read 0 — those are filtered. Prefer real non-zero RPM or duty %.
    """
    fans: list[dict] = []

    # NVIDIA GPU fan % when supported (often not on laptop GPUs)
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                try:
                    pct = pynvml.nvmlDeviceGetFanSpeed(handle)
                    fans.append(
                        safe_dict(
                            sensor="nvml",
                            label=f"{name} fan",
                            percent=int(pct),
                            unit="percent",
                            source="nvml",
                        )
                    )
                except Exception:
                    pass
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
    except Exception:
        pass

    # hwmon fan*_input (RPM) and pwm* (duty 0–255)
    hwmon = Path("/sys/class/hwmon")
    if hwmon.is_dir():
        for card in sorted(hwmon.glob("hwmon*")):
            chip = read_text(card / "name") or card.name
            for path in sorted(card.glob("fan*_input")):
                raw = read_text(path)
                if raw is None or not raw.lstrip("-").isdigit():
                    continue
                rpm = int(raw)
                if rpm <= 0:
                    continue  # fake/stuck ACPI zeros
                idx = path.name.replace("fan", "").replace("_input", "")
                label = read_text(card / f"fan{idx}_label") or f"{chip} fan{idx}"
                fans.append(
                    safe_dict(
                        sensor=chip,
                        label=label,
                        rpm=rpm,
                        unit="rpm",
                        source="hwmon",
                    )
                )
            for path in sorted(card.glob("pwm[0-9]")):
                raw = read_text(path)
                if raw is None or not raw.isdigit():
                    continue
                duty = int(raw)
                # 0 could be valid (fan off) but also common default — only show if enable says manual/active
                enable = read_text(Path(str(path) + "_enable"))
                if duty <= 0 and enable in (None, "0"):
                    continue
                pct = round(duty / 255 * 100)
                if pct <= 0:
                    continue
                fans.append(
                    safe_dict(
                        sensor=chip,
                        label=f"{chip} PWM",
                        percent=pct,
                        duty=duty,
                        unit="percent",
                        source="hwmon-pwm",
                    )
                )

    # psutil fallback — only non-zero
    try:
        for name, entries in (psutil.sensors_fans() or {}).items():
            for entry in entries:
                if entry.current is None or entry.current <= 0:
                    continue
                # skip duplicates already found via hwmon
                if any(f.get("rpm") == entry.current and f.get("sensor") == name for f in fans):
                    continue
                fans.append(
                    safe_dict(
                        sensor=name,
                        label=entry.label or name,
                        rpm=int(entry.current),
                        unit="rpm",
                        source="psutil",
                    )
                )
    except Exception:
        pass

    return fans


def get_vitals() -> dict:
    """Live metrics for the dashboard (poll ~1s)."""
    battery = None
    if hasattr(psutil, "sensors_battery"):
        bat = psutil.sensors_battery()
        if bat is not None:
            battery = safe_dict(
                percent=bat.percent,
                power_plugged=bat.power_plugged,
                secs_left=bat.secsleft if bat.secsleft and bat.secsleft >= 0 else None,
            )

    fans = collect_fans()

    all_temps = []
    try:
        for name, entries in (psutil.sensors_temperatures(fahrenheit=False) or {}).items():
            for entry in entries:
                all_temps.append(
                    safe_dict(
                        sensor=name,
                        label=entry.label or name,
                        celsius=round(entry.current, 1) if entry.current is not None else None,
                    )
                )
    except Exception:
        pass

    rates = _throughput()
    # Absolute counters so the UI can also compute rates client-side (more reliable across restarts)
    dr, dw = _disk_counters()
    nr, ns = _net_counters()

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "cpu": collect_cpu_vitals(),
        "memory": collect_memory_vitals(),
        "gpus": collect_gpus_vitals(),
        "storage": collect_storage_vitals(),
        "network": collect_network_vitals(),
        "rates": {
            "disk_read_mbs": rates.get("disk_read_mbs", 0.0),
            "disk_write_mbs": rates.get("disk_write_mbs", 0.0),
            "net_recv_mbs": rates.get("net_recv_mbs", 0.0),
            "net_sent_mbs": rates.get("net_sent_mbs", 0.0),
            "ready": bool(rates.get("ready")),
        },
        "counters": {
            "disk_read_bytes": dr,
            "disk_write_bytes": dw,
            "net_recv_bytes": nr,
            "net_sent_bytes": ns,
            "t_mono": time.monotonic(),
        },
        "battery": battery,
        "fans": fans,
        "fans_available": bool(fans),
        "temperatures": all_temps or None,
        "boot_time": psutil.boot_time(),
    }
