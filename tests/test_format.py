from backend.format import deg, fmt_uptime, format_human, pct


def test_pct_none():
    assert pct(None) == "—"


def test_pct_rounds():
    assert pct(42.4) == "42%"


def test_deg():
    assert deg(51.6) == "52°C"


def test_fmt_uptime_minutes_only():
    assert fmt_uptime(120) == "2 mins"


def test_fmt_uptime_days():
    text = fmt_uptime(90000)
    assert "day" in text
    assert "hour" in text


def test_format_human_error():
    out = format_human({"ok": False, "error": "nope", "hint": "try gpu"})
    assert "Error: nope" in out
    assert "Hint: try gpu" in out


def test_format_human_status():
    payload = {
        "ok": True,
        "resource": "status",
        "data": {
            "hostname": "testbox",
            "os": "Test OS",
            "cpu": "Fake CPU",
            "gpus": ["Fake GPU"],
            "ram_gb": 16,
            "uptime_seconds": 120,
            "live": {
                "cpu_percent": 10,
                "cpu_temp_c": 50,
                "gpu_percent": None,
                "gpu_temp_c": 40,
                "ram_percent": 60,
                "gpu_note": "no sensors",
            },
        },
    }
    out = format_human(payload, color=False)
    assert "Fake CPU" in out
    assert "no sensors" in out
    assert "Temps" in out
    assert "Uptime" in out
    assert "testbox" not in out
    assert "Test OS" not in out


def test_format_human_connections_lists_every_socket():
    payload = {
        "ok": True,
        "resource": "net",
        "fields": ["connections"],
        "data": {
            "connections": {
                "available": True,
                "total": 2,
                "connections": [
                    {
                        "type": "TCP",
                        "local": "127.0.0.1:1234",
                        "remote": "1.2.3.4:443",
                        "status": "ESTABLISHED",
                        "process": "firefox",
                        "pid": 100,
                        "health": "good",
                    },
                    {
                        "type": "TCP",
                        "local": "127.0.0.1:1235",
                        "remote": "1.2.3.4:80",
                        "status": "ESTABLISHED",
                        "process": "firefox",
                        "pid": 100,
                        "health": "good",
                    },
                ],
            }
        },
    }
    out = format_human(payload, color=False)
    assert "2 connections" in out
    assert "127.0.0.1:1234" in out
    assert "1.2.3.4:443" in out
    assert "127.0.0.1:1235" in out
    assert out.count("firefox") == 2


def test_format_human_temps_includes_extra_sensors():
    payload = {
        "ok": True,
        "resource": "temps",
        "data": {
            "cpu_c": 50,
            "gpus": [{"name": "RTX", "temp_c": 60}],
            "all_sensors": [
                {"label": "Composite", "sensor": "nvme", "celsius": 41.2},
                {"label": "Tctl", "sensor": "k10temp", "celsius": 50.0},
            ],
        },
    }
    out = format_human(payload, color=False)
    assert "Composite" in out
    assert "41°C" in out
    assert "Tctl" not in out


def test_format_human_disk_lists_all_partitions():
    payload = {
        "ok": True,
        "resource": "disk",
        "data": {
            "disks": [{"name": "sda", "size_gb": 500, "media": "SSD/NVMe"}],
            "partitions": [
                {"mountpoint": f"/m{i}", "percent": 10, "used_gb": 1, "total_gb": 10, "fstype": "ext4"}
                for i in range(10)
            ],
            "rates_mbs": {"read": 0, "write": 0},
        },
    }
    out = format_human(payload, color=False)
    assert "/m0" in out
    assert "/m9" in out
    assert "ext4" in out


def test_format_human_scan_lists_components():
    payload = {
        "ok": True,
        "resource": "scan",
        "data": {
            "summary": {"hostname": "box", "os": "Linux", "cpu": "CPU", "gpus": [], "ram_gb": 8},
            "counts": {"total_components": 2},
            "components": [
                {"category": "cpu", "name": "Ryzen"},
                {"category": "disk", "name": "Samsung SSD"},
            ],
        },
    }
    out = format_human(payload, color=False)
    assert "Ryzen" in out
    assert "Samsung SSD" in out


def test_format_human_scan_lists_displays():
    payload = {
        "ok": True,
        "resource": "scan",
        "data": {
            "summary": {"hostname": "box", "os": "Linux", "cpu": "CPU", "gpus": [], "ram_gb": 8},
            "counts": {"total_components": 1},
            "components": [
                {"category": "display", "name": "BOE panel", "connector": "eDP-1"},
            ],
        },
    }
    out = format_human(payload, color=False)
    assert "BOE panel" in out
    assert "display" in out


def test_format_human_gpu_shows_note_when_no_sensors():
    payload = {
        "ok": True,
        "resource": "gpu",
        "data": {
            "count": 1,
            "devices": [
                {
                    "name": "RTX 4050",
                    "usage_percent": None,
                    "temp_c": None,
                    "vram_total_mb": None,
                    "note": "PCI only · NVIDIA driver/NVML unavailable",
                }
            ],
        },
    }
    out = format_human(payload, color=False)
    assert "PCI only" in out
