from __future__ import annotations

import re
from pathlib import Path

from .util import read_text, run_cmd, safe_dict


def collect_gpus_inventory() -> list[dict]:
    """Discover GPUs without hardcoding a specific card."""
    gpus: list[dict] = []
    pci_ids_seen: set[str] = set()
    vendors_from_nvml: set[str] = set()

    for gpu in _from_nvidia_nvml():
        gpus.append(gpu)
        vendors_from_nvml.add("nvidia")
        if gpu.get("pci_id"):
            pci_ids_seen.add(gpu["pci_id"].lower())

    for gpu in _from_lspci():
        pci_id = (gpu.get("pci_id") or "").lower()
        vendor = (gpu.get("vendor") or "").lower()
        # NVML already gave a clean NVIDIA name; keep lspci marketing string as note on existing
        if vendor == "nvidia" and "nvidia" in vendors_from_nvml:
            if pci_id:
                pci_ids_seen.add(pci_id)
            # Attach lspci name onto first NVIDIA entry if useful
            for existing in gpus:
                if (existing.get("vendor") or "").lower() == "nvidia" and not existing.get(
                    "pci_name"
                ):
                    existing["pci_name"] = gpu.get("name")
                    if gpu.get("pci_slot"):
                        existing["pci_slot"] = gpu.get("pci_slot")
                    if pci_id:
                        existing["pci_id"] = pci_id
                    break
            continue
        if pci_id and pci_id in pci_ids_seen:
            continue
        if pci_id:
            pci_ids_seen.add(pci_id)
        gpus.append(gpu)

    # DRM only when we still lack a vendor GPU (rare)
    if not gpus:
        gpus.extend(_from_drm())
    else:
        # Prefer not listing raw card0 when lspci/NVML already covered display GPUs
        pass

    return gpus or [
        safe_dict(
            category="gpu",
            name="No GPU detected",
            note="No NVML, lspci VGA device, or DRM card found.",
        )
    ]


def collect_gpus_vitals() -> list[dict]:
    """Live GPU stats where available (NVIDIA best; others best-effort)."""
    vitals = _nvidia_vitals()
    if vitals:
        return vitals

    # AMD/Intel: temperatures from hwmon + rough load if available
    return _fallback_vitals_from_hwmon()


def _from_nvidia_nvml() -> list[dict]:
    try:
        import pynvml
    except ImportError:
        return []

    try:
        pynvml.nvmlInit()
    except Exception:
        return []

    out: list[dict] = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = _nvml_str(pynvml.nvmlDeviceGetName(handle))
            uuid = None
            try:
                uuid = _nvml_str(pynvml.nvmlDeviceGetUUID(handle))
            except Exception:
                pass
            mem = None
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            except Exception:
                pass
            driver = None
            try:
                driver = _nvml_str(pynvml.nvmlSystemGetDriverVersion())
            except Exception:
                pass
            cuda = None
            try:
                cuda = _nvml_str(pynvml.nvmlSystemGetCudaDriverVersion_v2())
            except Exception:
                try:
                    major = pynvml.nvmlSystemGetCudaDriverVersion() // 1000
                    minor = (pynvml.nvmlSystemGetCudaDriverVersion() % 1000) // 10
                    cuda = f"{major}.{minor}"
                except Exception:
                    pass
            pci = None
            try:
                pci = _nvml_str(pynvml.nvmlDeviceGetPciInfo(handle).busId)
            except Exception:
                pass
            arch = None
            try:
                arch = pynvml.nvmlDeviceGetArchitecture(handle)
            except Exception:
                pass

            out.append(
                safe_dict(
                    category="gpu",
                    vendor="NVIDIA",
                    name=name,
                    index=i,
                    uuid=uuid,
                    driver_version=driver,
                    cuda_driver_version=str(cuda) if cuda is not None else None,
                    pci_bus_id=pci,
                    vram_total_bytes=mem.total if mem else None,
                    vram_total_mb=round(mem.total / (1024**2), 1) if mem else None,
                    architecture_id=arch,
                    source="nvml",
                )
            )
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return out


def _nvidia_vitals() -> list[dict]:
    try:
        import pynvml
    except ImportError:
        # Fall back to nvidia-smi once
        return _nvidia_smi_vitals()

    try:
        pynvml.nvmlInit()
    except Exception:
        return _nvidia_smi_vitals()

    out: list[dict] = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = _nvml_str(pynvml.nvmlDeviceGetName(handle))
            util = None
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            except Exception:
                pass
            mem = None
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            except Exception:
                pass
            temp = None
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except Exception:
                pass
            power = None
            try:
                power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            except Exception:
                pass
            power_limit = None
            try:
                power_limit = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle) / 1000.0
            except Exception:
                pass
            clocks = {}
            for label, clock_type in (
                ("graphics_mhz", getattr(pynvml, "NVML_CLOCK_GRAPHICS", 0)),
                ("mem_mhz", getattr(pynvml, "NVML_CLOCK_MEM", 2)),
            ):
                try:
                    clocks[label] = pynvml.nvmlDeviceGetClockInfo(handle, clock_type)
                except Exception:
                    pass
            fan = None
            try:
                fan = pynvml.nvmlDeviceGetFanSpeed(handle)
            except Exception:
                pass

            out.append(
                safe_dict(
                    vendor="NVIDIA",
                    name=name,
                    index=i,
                    usage_percent=util.gpu if util else None,
                    memory_usage_percent=util.memory if util else None,
                    vram_used_bytes=mem.used if mem else None,
                    vram_total_bytes=mem.total if mem else None,
                    vram_used_mb=round(mem.used / (1024**2), 1) if mem else None,
                    vram_total_mb=round(mem.total / (1024**2), 1) if mem else None,
                    temperature_c=temp,
                    power_watts=round(power, 1) if power is not None else None,
                    power_limit_watts=round(power_limit, 1) if power_limit is not None else None,
                    fan_percent=fan,
                    **clocks,
                    source="nvml",
                )
            )
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return out


def _nvidia_smi_vitals() -> list[dict]:
    raw = run_cmd(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,power.limit",
            "--format=csv,noheader,nounits",
        ]
    )
    if not raw:
        return []
    out: list[dict] = []
    for i, line in enumerate(raw.splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue

        def num(idx: int) -> float | None:
            try:
                return float(parts[idx])
            except (ValueError, IndexError):
                return None

        out.append(
            safe_dict(
                vendor="NVIDIA",
                name=parts[0],
                index=i,
                usage_percent=num(1),
                memory_usage_percent=num(2),
                vram_used_mb=num(3),
                vram_total_mb=num(4),
                temperature_c=num(5),
                power_watts=num(6),
                power_limit_watts=num(7) if len(parts) > 7 else None,
                source="nvidia-smi",
            )
        )
    return out


def _from_lspci() -> list[dict]:
    raw = run_cmd(["lspci", "-nn"])
    if not raw:
        return []
    out: list[dict] = []
    # VGA / 3D / Display — class code like [0300] may sit before the colon
    pattern = re.compile(
        r"^([0-9a-f:.]+)\s+"
        r"(VGA compatible controller|3D controller|Display controller)"
        r"(?:\s+\[[0-9a-f]+\])?\s*:\s*(.+)$",
        re.IGNORECASE,
    )
    for line in raw.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        slot, kind, rest = m.group(1), m.group(2), m.group(3)
        vendor = "Unknown"
        low = rest.lower()
        if "nvidia" in low:
            vendor = "NVIDIA"
        elif "amd" in low or "ati" in low:
            vendor = "AMD"
        elif "intel" in low:
            vendor = "Intel"
        # Strip PCI ID brackets for a cleaner name, keep id separately
        pci_id = None
        id_match = re.search(r"\[([0-9a-f]{4}:[0-9a-f]{4})\]", rest, re.I)
        if id_match:
            pci_id = id_match.group(1)
        name = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]\s*", " ", rest, flags=re.I).strip()
        out.append(
            safe_dict(
                category="gpu",
                vendor=vendor,
                name=name,
                pci_slot=slot,
                pci_id=pci_id,
                device_class=kind,
                source="lspci",
            )
        )
    return out


def _from_drm() -> list[dict]:
    drm = Path("/sys/class/drm")
    if not drm.is_dir():
        return []
    out: list[dict] = []
    for card in sorted(drm.glob("card[0-9]")):
        if "-" in card.name:
            continue
        # vendor/device from device
        device = card / "device"
        vendor_id = read_text(device / "vendor")
        device_id = read_text(device / "device")
        driver = None
        driver_link = device / "driver"
        if driver_link.exists():
            try:
                driver = driver_link.resolve().name
            except OSError:
                pass
        uevent = read_text(device / "uevent") or ""
        modalias = None
        for line in uevent.splitlines():
            if line.startswith("DRIVER="):
                driver = driver or line.split("=", 1)[1]
            if line.startswith("PCI_ID="):
                modalias = line.split("=", 1)[1]
        name = f"DRM {card.name}"
        if modalias:
            name = f"{card.name} ({modalias})"
        out.append(
            safe_dict(
                category="gpu",
                name=name,
                drm_card=card.name,
                vendor_id=vendor_id,
                device_id=device_id,
                driver=driver,
                source="drm",
            )
        )
    return out


def _fallback_vitals_from_hwmon() -> list[dict]:
    try:
        import psutil
    except ImportError:
        return []
    readings = psutil.sensors_temperatures(fahrenheit=False) or {}
    out: list[dict] = []
    for name, entries in readings.items():
        low = name.lower()
        if not any(x in low for x in ("amdgpu", "radeon", "i915", "xe", "gpu")):
            continue
        for entry in entries:
            out.append(
                safe_dict(
                    vendor=name,
                    name=entry.label or name,
                    temperature_c=round(entry.current, 1) if entry.current is not None else None,
                    source="hwmon",
                )
            )
    return out


def _nvml_str(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
