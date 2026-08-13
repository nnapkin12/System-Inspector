import threading
import time
from unittest.mock import patch

from backend import live_query


def teardown_function():
    live_query.reset_for_tests()


def test_timeout_returns_before_worker_finishes():
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def slow(*_a, **_k):
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return {"ok": True, "resource": "gpu"}

    live_query.reset_for_tests()
    try:
        with patch("backend.resources.run_query", side_effect=slow):
            t0 = time.monotonic()
            payload, timed_out = live_query.run_query_timed(["gpu"], timeout=0.12)
            elapsed = time.monotonic() - t0
            assert timed_out is True
            assert payload is None
            assert elapsed < 0.5
            assert started.wait(1.0)

            _, timed_out2 = live_query.run_query_timed(["gpu"], timeout=0.08)
            assert timed_out2 is True
            assert len(calls) == 1

            release.set()
            time.sleep(0.05)
            payload3, timed_out3 = live_query.run_query_timed(["gpu"], timeout=0.12)
            assert timed_out3 is False
            assert payload3 and payload3.get("ok") is True
    finally:
        release.set()
