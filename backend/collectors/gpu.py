from __future__ import annotations

import re
import threading
from pathlib import Path

from .util import read_text, run_cmd, safe_dict, sensors_temperatures

_nvml_lock = threading.Lock()
_nvml_live = False


def nvml_live_begin() -> None:
    """Keep NVML open for live polling — avoids init/shutdown every tick."""
    global _nvml_live
    with _nvml_lock:
        if _nvml_live:
            return
        try:
            import pynvml

            pynvml.nvmlInit()
            _nvml_live = True
        except Exception:
            pass


def nvml_live_end() -> None:
    global _nvml_live
    with _nvml_lock:
        if not _nvml_live:
            return
        try:
            import pynvml

            pynvml.nvmlShutdown()
        except Exception:
            pass
        _nvml_live = False


def reset_nvml_live_for_tests() -> None:
    nvml_live_end()


def _nvml_acquire():
    """Open NVML only if live mode is not already holding it."""
    try:
        import pynvml
    except ImportError:
        return None, False
    with _nvml_lock:
        if _nvml_live:
            return pynvml, False
        try:
            pynvml.nvmlInit()
            return pynvml, True
        except Exception:
            return None, False


def _nvml_release(pynvml, owns_session: bool) -> None:
    if not owns_session or pynvml is None:
        return
    try:
        pynvml.nvmlShutdown()
    except Exception:
        pass


def normalize_pci_bdf(s: str | None) -> str | None:
    """Canonical PCI BDF: 01:00.0 and 00000000:01:00.0 → 0000:01:00.0."""
    if not s:
        return None
    text = str(s).strip().lower()
    m = re.fullmatch(
        r"(?:([0-9a-f]+):)?([0-9a-f]{1,2}):([0-9a-f]{1,2})\.([0-9a-f]+)",
        text,
    )
    if not m:
        return text or None
    domain, bus, dev, fn = m.groups()
    if domain is None:
        domain = "0000"
    else:
        domain = domain[-4:].zfill(4)
    return f"{domain}:{bus.zfill(2)}:{dev.zfill(2)}.{fn}"


def merge_gpu_inventory(nvml: list[dict], lspci: list[dict]) -> list[dict]:
    """Join NVML inventory with lspci rows, matching NVIDIA cards by PCI BDF."""
    gpus = [dict(g) for g in nvml]
    has_nvml_nvidia = any((g.get("vendor") or "").lower() == "nvidia" for g in gpus)
    seen_bdf = {
        bdf
        for g in gpus
        if (bdf := normalize_pci_bdf(g.get("pci_bus_id") or g.get("pci_slot")))
    }
    seen_pci_id = {(g.get("pci_id") or "").lower() for g in gpus if g.get("pci_id")}

    for gpu in lspci:
        pci_id = (gpu.get("pci_id") or "").lower()
        vendor = (gpu.get("vendor") or "").lower()
        slot = normalize_pci_bdf(gpu.get("pci_slot"))

        if vendor == "nvidia" and has_nvml_nvidia:
            attached = False
            if slot:
                for existing in gpus:
                    exist_slot = normalize_pci_bdf(
                        existing.get("pci_bus_id") or existing.get("pci_slot")
                    )
                    if exist_slot == slot:
                        if not existing.get("pci_name"):
                            existing["pci_name"] = gpu.get("name")
                        existing["pci_slot"] = gpu.get("pci_slot")
                        if pci_id:
                            existing["pci_id"] = pci_id
                        attached = True
                        break
            if attached:
                if slot:
                    seen_bdf.add(slot)
                if pci_id:
                    seen_pci_id.add(pci_id)
                continue
            if slot and slot in seen_bdf:
                continue
            gpus.append(gpu)
            if slot:
                seen_bdf.add(slot)
            if pci_id:
                seen_pci_id.add(pci_id)
            continue

        if slot and slot in seen_bdf:
            continue
        if not slot and pci_id and pci_id in seen_pci_id:
            continue
        gpus.append(gpu)
        if slot:
            seen_bdf.add(slot)
        if pci_id:
            seen_pci_id.add(pci_id)
    return gpus


def collect_gpus_inventory() -> list[dict]:
    """Discover GPUs without hardcoding a specific card."""
    gpus = merge_gpu_inventory(_from_nvidia_nvml(), _from_lspci())
    if not gpus:
        gpus.extend(_from_drm())
    return gpus or [
        safe_dict(
            category="gpu",
            name="No GPU detected",
            note="No NVML, lspci VGA device, or DRM card found.",
        )
    ]


def collect_gpus_vitals() -> list[dict]:
    """Live GPU stats where available (NVIDIA + AMD/Intel best-effort).

    Never drop iGPU temps just because discrete NVML exists, and never
    invent an NVIDIA reading from a lone amdgpu hwmon sensor.
    """
    out: list[dict] = []
    seen_labels: set[str] = set()

    for g in _nvidia_vitals() or []:
        key = (g.get("name") or f"nvidia-{g.get('index')}").lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        out.append(g)

    for g in _fallback_vitals_from_hwmon() or []:
        key = f"{(g.get('vendor') or '').lower()}:{(g.get('name') or '').lower()}"
        if key in seen_labels:
            continue
        seen_labels.add(key)
        out.append(g)

    return out


def _from_nvidia_nvml() -> list[dict]:
    pynvml, owns_session = _nvml_acquire()
    if pynvml is None:
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
        _nvml_release(pynvml, owns_session)
    return out


def _nvidia_vitals() -> list[dict]:
    pynvml, owns_session = _nvml_acquire()
    if pynvml is None:
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
            pci_bus = None
            try:
                pci_bus = _nvml_str(pynvml.nvmlDeviceGetPciInfo(handle).busId)
            except Exception:
                pass

            out.append(
                safe_dict(
                    vendor="NVIDIA",
                    name=name,
                    index=i,
                    pci_bus_id=pci_bus,
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
        _nvml_release(pynvml, owns_session)
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
        raw_name = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]\s*", " ", rest, flags=re.I).strip()
        name = short_gpu_name(raw_name) or raw_name
        out.append(
            safe_dict(
                category="gpu",
                vendor=vendor,
                name=name,
                pci_name=raw_name,
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
    readings = sensors_temperatures()
    out: list[dict] = []
    for chip, entries in readings.items():
        low = chip.lower()
        if not any(x in low for x in ("amdgpu", "radeon", "i915", "xe", "nouveau", "gpu")):
            continue
        vendor = "AMD" if any(x in low for x in ("amd", "radeon")) else (
            "Intel" if any(x in low for x in ("i915", "xe")) else chip
        )
        # Prefer a junction/edge reading over every redundant sensor
        best = None
        for entry in entries:
            if entry.current is None:
                continue
            label = (entry.label or chip).lower()
            score = 0
            if "edge" in label or "junction" in label or "gpu" in label:
                score = 2
            elif "mem" in label:
                score = 1
            cand = (score, entry.current, entry.label or chip)
            if best is None or cand[0] > best[0] or (cand[0] == best[0] and cand[1] > best[1]):
                best = cand
        if best is None:
            continue
        out.append(
            safe_dict(
                vendor=vendor,
                name=f"{vendor} iGPU" if vendor in ("AMD", "Intel") else best[2],
                temperature_c=round(best[1], 1),
                source="hwmon",
            )
        )
    return out


def short_gpu_name(name: str | None) -> str:
    """
    Turn noisy lspci strings into something readable on one line.
    e.g. 'NVIDIA Corporation AD107M [GeForce RTX 4050 Max-Q / Mobile] (rev a1)'
      → 'GeForce RTX 4050 Max-Q / Mobile'
    """
    if not name:
        return "GPU"
    s = str(name).strip()
    brand_tags = {"amd/ati", "amd", "ati", "nvidia", "intel", "via"}
    # Prefer meaningful [product] brackets (skip short brand tags + PCI ids)
    for cand in re.findall(r"\[([^\]]{2,})\]", s):
        if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{4}", cand, re.I):
            continue
        if cand.strip().lower() in brand_tags:
            continue
        if len(cand.strip()) < 4:
            continue
        s = cand.strip()
        break
    else:
        s = re.sub(r"^NVIDIA Corporation\s+", "", s, flags=re.I)
        s = re.sub(r"^Advanced Micro Devices,\s*Inc\.\s*", "", s, flags=re.I)
        s = re.sub(r"^\[?AMD/?ATI\]?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]\s*", " ", s, flags=re.I)
        s = re.sub(r"\s*\[AMD/?ATI\]\s*", " ", s, flags=re.I)
        s = re.sub(r"\s*\(rev\s+[0-9a-f]+\)$", "", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip()
    return (s or "GPU")[:48]


def _nvml_str(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
