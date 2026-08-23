from unittest.mock import patch

from backend.live_query import InventoryCache
from backend.resources import run_query
from backend.snapshot import Snapshot


def test_inventory_cache_reuses_within_ttl():
    cache = InventoryCache(ttl=30.0)
    first = {"summary": {"cpu": "Fake"}, "components": []}

    with patch("backend.snapshot.get_inventory", return_value=first) as inv:
        snap1 = cache.make_snapshot()
        assert snap1.inventory() is first
        cache.remember(snap1)
        assert inv.call_count == 1

        snap2 = cache.make_snapshot()
        assert snap2.peek_inventory() is first
        assert snap2.inventory() is first
        assert inv.call_count == 1


def test_run_query_reuses_passed_snapshot_inventory():
    snap = Snapshot()
    snap.reuse_inventory(
        {
            "summary": {
                "hostname": "box",
                "os": "TestOS",
                "cpu": "FakeCPU",
                "gpus": [],
                "ram_gb": 8,
                "uptime_seconds": 10,
            },
            "components": [],
        }
    )
    vitals = {
        "cpu": {"usage_percent": 4, "temperatures": [{"celsius": 40}]},
        "memory": {"ram": {"percent": 20}},
        "gpus": [],
    }
    with patch("backend.snapshot.get_inventory") as inv:
        with patch("backend.snapshot.get_vitals", return_value=vitals):
            out = run_query(["status"], snap=snap)
    assert inv.call_count == 0
    assert out["ok"] is True
    assert out["data"]["hostname"] == "box"
    assert out["data"]["live"]["cpu_percent"] == 4


def test_status_gpu_temp_does_not_borrow_igpu():
    snap = Snapshot()
    snap.reuse_inventory(
        {
            "summary": {
                "hostname": "box",
                "os": "TestOS",
                "cpu": "FakeCPU",
                "gpus": ["RTX", "Phoenix"],
                "ram_gb": 8,
            },
            "components": [],
        }
    )
    vitals = {
        "cpu": {"usage_percent": 4, "temperatures": [{"celsius": 40}]},
        "memory": {"ram": {"percent": 20}, "swap": {}},
        "gpus": [
            {"vendor": "NVIDIA", "name": "RTX", "usage_percent": 12, "temperature_c": None},
            {"vendor": "AMD", "name": "Phoenix", "temperature_c": 42},
        ],
        "rates": {},
        "battery": None,
    }
    with patch("backend.snapshot.get_inventory") as inv:
        with patch("backend.snapshot.get_vitals", return_value=vitals):
            out = run_query(["status"], snap=snap)
    assert inv.call_count == 0
    live = out["data"]["live"]
    assert live["gpu_percent"] == 12
    assert live["gpu_temp_c"] is None
