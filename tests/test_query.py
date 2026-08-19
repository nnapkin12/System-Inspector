from backend.query import parse_query
from backend.resources import apply_fields, run_query


def test_parse_gpu_temp():
    resources, fields, unknown = parse_query(["gpu", "temp"])
    assert resources == ["gpu"]
    assert fields == {"temp"}
    assert unknown == []


def test_parse_bare_kernel_is_os_slice():
    resources, fields, unknown = parse_query(["kernel"])
    assert resources == ["os"]
    assert fields == {"kernel"}
    assert unknown == []


def test_parse_version_is_app_not_os():
    resources, fields, unknown = parse_query(["version"])
    assert resources == ["version"]
    assert fields == set()
    assert unknown == []


def test_parse_os_version_is_distro_field():
    resources, fields, unknown = parse_query(["os", "version"])
    assert resources == ["os"]
    assert fields == {"version"}
    assert unknown == []


def test_parse_net_ip():
    resources, fields, unknown = parse_query(["net", "ip"])
    assert resources == ["net"]
    assert fields == {"ip"}
    assert unknown == []


def test_parse_unknown_only():
    resources, fields, unknown = parse_query(["foobar"])
    assert resources == []
    assert fields == set()
    assert unknown == ["foobar"]


def test_run_query_unknown():
    out = run_query(["not-a-real-command"])
    assert out["ok"] is False
    assert "Unknown" in out["error"]


def test_apply_fields_cpu_temp():
    payload = {
        "ok": True,
        "resource": "cpu",
        "data": {
            "name": "Test CPU",
            "temp_c": 55.0,
            "usage_percent": 10,
            "temperatures": [{"celsius": 55.0}],
        },
    }
    out = apply_fields(payload, {"temp"})
    assert out["data"]["temp_c"] == 55.0
    assert "usage_percent" not in out["data"]


def test_apply_fields_cpu_temp_usage():
    payload = {
        "ok": True,
        "resource": "cpu",
        "data": {
            "name": "Test CPU",
            "temp_c": 55.0,
            "usage_percent": 10,
            "temperatures": [{"celsius": 55.0}],
        },
    }
    out = apply_fields(payload, {"temp", "usage"})
    assert out["data"]["temp"]["temp_c"] == 55.0
    assert out["data"]["usage"]["usage_percent"] == 10


def test_apply_fields_gpu_temp_keeps_note():
    payload = {
        "ok": True,
        "resource": "gpu",
        "data": {
            "devices": [
                {
                    "name": "RTX 4050",
                    "temp_c": None,
                    "note": "PCI only · NVIDIA driver/NVML unavailable",
                }
            ]
        },
    }
    out = apply_fields(payload, {"temp"})
    assert out["data"]["devices"][0]["note"] == "PCI only · NVIDIA driver/NVML unavailable"


def test_apply_fields_gpu_usage_keeps_note():
    payload = {
        "ok": True,
        "resource": "gpu",
        "data": {
            "devices": [
                {
                    "name": "RTX 4050",
                    "usage_percent": None,
                    "note": "PCI only · NVIDIA driver/NVML unavailable",
                }
            ]
        },
    }
    out = apply_fields(payload, {"usage"})
    assert out["data"]["devices"][0]["note"] == "PCI only · NVIDIA driver/NVML unavailable"
