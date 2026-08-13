from unittest.mock import patch

from backend.resources import resource_all, run_query
from backend.snapshot import Snapshot


def test_run_query_catches_collector_exceptions():
    with patch("backend.resources.get_resource") as get_resource:
        get_resource.side_effect = RuntimeError("nvml blew up")
        out = run_query(["gpu"])
    assert out["ok"] is False
    assert out["resource"] == "gpu"
    assert "RuntimeError" in out["error"]


def test_resource_all_keeps_other_sections_if_one_throws():
    snap = Snapshot()
    with patch("backend.resources.resource_cpu", side_effect=RuntimeError("cpu collector died")):
        out = resource_all(snap)
    assert out["ok"] is True
    assert out["data"]["cpu"]["ok"] is False
    assert "RuntimeError" in out["data"]["cpu"]["error"]
    assert "hostname" in (out["data"].get("status") or {})
