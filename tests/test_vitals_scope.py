from unittest.mock import patch

from backend.collectors.vitals import get_vitals
from backend.query import vitals_needs_for, vitals_needs_for_tokens


def test_vitals_needs_gpu_only():
    assert vitals_needs_for(["gpu"]) == frozenset({"gpus"})
    assert vitals_needs_for_tokens(["gpu", "temp"]) == frozenset({"gpus"})


def test_vitals_needs_status_union():
    needs = vitals_needs_for(["cpu", "gpu"])
    assert needs == frozenset({"cpu", "gpus"})


def test_vitals_needs_status_is_cheap():
    needs = vitals_needs_for(["status"])
    assert needs == frozenset({"cpu", "memory", "gpus", "rates", "battery"})
    assert "fans" not in needs
    assert "temperatures" not in needs


def test_get_vitals_partial_skips_fans():
    with patch("backend.collectors.vitals.collect_gpus_vitals", return_value=[{"name": "GPU"}]):
        with patch("backend.collectors.vitals.collect_fans") as fans:
            with patch("backend.collectors.vitals.collect_cpu_vitals", return_value={"usage_percent": 1}):
                out = get_vitals(frozenset({"gpus"}))
    fans.assert_not_called()
    assert "gpus" in out
    assert "fans" not in out
    assert "cpu" not in out
