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
    assert "testbox" in out
    assert "Fake CPU" in out
    assert "no sensors" in out


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
