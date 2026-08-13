from backend.collectors.gpu import merge_gpu_inventory, normalize_pci_bdf
from backend.resources import merge_gpu_devices


def test_merge_gpu_devices_pairs_inventory_and_live():
    inv = {
        "components": [
            {
                "category": "gpu",
                "name": "GeForce RTX 4050",
                "vendor": "NVIDIA",
                "pci_id": "10de:1234",
                "source": "lspci",
            }
        ]
    }
    vit = {
        "gpus": [
            {
                "vendor": "NVIDIA",
                "name": "GeForce RTX 4050 Laptop GPU",
                "usage_percent": 12,
                "temperature_c": 41,
                "vram_total_mb": 8188,
                "source": "nvml",
            }
        ]
    }
    devices = merge_gpu_devices(inv, vit)
    assert len(devices) == 1
    assert devices[0]["usage_percent"] == 12
    assert devices[0]["temp_c"] == 41


def test_merge_dual_identical_nvidia_by_pci_bdf():
    inv = {
        "components": [
            {
                "category": "gpu",
                "name": "GeForce RTX 4090",
                "vendor": "NVIDIA",
                "pci_id": "10de:2684",
                "pci_slot": "0000:01:00.0",
                "source": "lspci",
            },
            {
                "category": "gpu",
                "name": "GeForce RTX 4090",
                "vendor": "NVIDIA",
                "pci_id": "10de:2684",
                "pci_slot": "0000:02:00.0",
                "source": "lspci",
            },
        ]
    }
    vit = {
        "gpus": [
            {
                "vendor": "NVIDIA",
                "name": "GeForce RTX 4090",
                "index": 0,
                "pci_bus_id": "0000:01:00.0",
                "usage_percent": 10,
                "temperature_c": 55,
                "source": "nvml",
            },
            {
                "vendor": "NVIDIA",
                "name": "GeForce RTX 4090",
                "index": 1,
                "pci_bus_id": "0000:02:00.0",
                "usage_percent": 20,
                "temperature_c": 60,
                "source": "nvml",
            },
        ]
    }
    devices = merge_gpu_devices(inv, vit)
    assert len(devices) == 2
    by_usage = sorted(d.get("usage_percent") for d in devices)
    assert by_usage == [10, 20]


def test_merge_igpu_and_dgpu_laptop():
    inv = {
        "components": [
            {
                "category": "gpu",
                "name": "GeForce RTX 4050",
                "vendor": "NVIDIA",
                "pci_id": "10de:28a0",
                "pci_slot": "0000:01:00.0",
                "source": "lspci",
            },
            {
                "category": "gpu",
                "name": "AMD Phoenix4",
                "vendor": "AMD",
                "pci_id": "1002:15bf",
                "pci_slot": "0000:06:00.0",
                "source": "lspci",
            },
        ]
    }
    vit = {
        "gpus": [
            {
                "vendor": "NVIDIA",
                "name": "GeForce RTX 4050 Laptop GPU",
                "index": 0,
                "pci_bus_id": "0000:01:00.0",
                "usage_percent": 15,
                "temperature_c": 48,
                "source": "nvml",
            },
            {
                "vendor": "AMD",
                "name": "AMD Phoenix4",
                "temperature_c": 42,
                "source": "hwmon",
            },
        ]
    }
    devices = merge_gpu_devices(inv, vit)
    assert len(devices) == 2
    nvidia = next(d for d in devices if (d.get("vendor") or "").upper() == "NVIDIA")
    amd = next(d for d in devices if (d.get("vendor") or "").upper() == "AMD")
    assert nvidia["usage_percent"] == 15
    assert nvidia["temp_c"] == 48
    assert amd["temp_c"] == 42


def test_normalize_pci_bdf_short_and_long():
    assert normalize_pci_bdf("01:00.0") == "0000:01:00.0"
    assert normalize_pci_bdf("0000:01:00.0") == "0000:01:00.0"
    assert normalize_pci_bdf("00000000:01:00.0") == "0000:01:00.0"
    assert normalize_pci_bdf(None) is None


def test_merge_gpu_devices_matches_short_lspci_bdf_to_nvml():
    inv = {
        "components": [
            {
                "category": "gpu",
                "name": "GeForce RTX 4050",
                "vendor": "NVIDIA",
                "pci_slot": "01:00.0",
                "source": "lspci",
            }
        ]
    }
    vit = {
        "gpus": [
            {
                "vendor": "NVIDIA",
                "name": "GeForce RTX 4050 Laptop GPU",
                "pci_bus_id": "0000:01:00.0",
                "usage_percent": 22,
                "temperature_c": 50,
                "source": "nvml",
            }
        ]
    }
    devices = merge_gpu_devices(inv, vit)
    assert len(devices) == 1
    assert devices[0]["usage_percent"] == 22


def test_merge_gpu_inventory_pairs_nvml_and_lspci_by_bdf_not_order():
    nvml = [
        {
            "category": "gpu",
            "vendor": "NVIDIA",
            "name": "NVIDIA GeForce RTX 4090",
            "index": 0,
            "pci_bus_id": "0000:01:00.0",
            "source": "nvml",
        },
        {
            "category": "gpu",
            "vendor": "NVIDIA",
            "name": "NVIDIA GeForce RTX 4090",
            "index": 1,
            "pci_bus_id": "0000:02:00.0",
            "source": "nvml",
        },
    ]
    lspci = [
        {
            "category": "gpu",
            "vendor": "NVIDIA",
            "name": "slot-b",
            "pci_slot": "02:00.0",
            "pci_id": "10de:2684",
            "source": "lspci",
        },
        {
            "category": "gpu",
            "vendor": "NVIDIA",
            "name": "slot-a",
            "pci_slot": "01:00.0",
            "pci_id": "10de:2684",
            "source": "lspci",
        },
    ]
    gpus = merge_gpu_inventory(nvml, lspci)
    assert len(gpus) == 2
    by_index = {g["index"]: g for g in gpus}
    assert by_index[0]["pci_slot"] == "01:00.0"
    assert by_index[0]["pci_name"] == "slot-a"
    assert by_index[1]["pci_slot"] == "02:00.0"
    assert by_index[1]["pci_name"] == "slot-b"
