from backend.smooth import MetricSmoother


def test_smoother_first_sample_is_raw():
    s = MetricSmoother()
    assert s.value("gpu", 30) == 30


def test_smoother_default_interval_stays_close_to_raw():
    s = MetricSmoother()
    s.value("gpu", 30, dt=1.0)
    out = s.value("gpu", 45, dt=1.0)
    assert out is not None
    # 1s tick + short tau ≈ the new reading, not a mid-30s smear
    assert out >= 42


def test_smoother_fast_refresh_damps_small_jitter():
    s = MetricSmoother()
    s.value("gpu", 30, dt=0.25)
    mid = s.value("gpu", 45, dt=0.25)
    assert mid is not None
    assert 30 < mid < 45


def test_smoother_snaps_real_load_jumps():
    s = MetricSmoother()
    s.value("gpu", 10, dt=1.0)
    assert s.value("gpu", 80, dt=1.0) == 80


def test_smoother_skips_none():
    s = MetricSmoother()
    assert s.value("gpu", None) is None
    assert s.value("gpu", 20) == 20


def test_smoother_status_payload_only_touches_load():
    s = MetricSmoother()
    s.apply_payload(
        {
            "ok": True,
            "resource": "status",
            "data": {
                "live": {
                    "cpu_percent": 40,
                    "gpu_percent": 40,
                    "cpu_temp_c": 55,
                    "ram_percent": 41,
                }
            },
        },
        dt=0.25,
    )
    out = s.apply_payload(
        {
            "ok": True,
            "resource": "status",
            "data": {
                "live": {
                    "cpu_percent": 48,
                    "gpu_percent": 48,
                    "cpu_temp_c": 70,
                    "ram_percent": 90,
                }
            },
        },
        dt=0.25,
    )
    live = out["data"]["live"]
    assert live["cpu_percent"] < 48
    assert live["gpu_percent"] < 48
    assert live["cpu_temp_c"] == 70
    assert live["ram_percent"] == 90
