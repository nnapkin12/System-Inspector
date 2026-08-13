"""Wall-clock timeout wrapper for live-mode queries."""

from __future__ import annotations

import atexit
import threading
from concurrent import futures
from typing import Any

LIVE_QUERY_TIMEOUT = 2.5

_lock = threading.Lock()
_pool: futures.ThreadPoolExecutor | None = None
_fut: futures.Future | None = None
_fut_key: tuple | None = None


def _executor() -> futures.ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="si-live")
    return _pool


def _query_key(tokens: list[str], kwargs: dict[str, Any]) -> tuple:
    return (tuple(tokens), tuple(sorted((k, repr(v)) for k, v in kwargs.items())))


def reset_for_tests() -> None:
    """Drop in-flight state. Test-only."""
    global _pool, _fut, _fut_key
    with _lock:
        _fut = None
        _fut_key = None
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=False)
            _pool = None


def _shutdown_pool() -> None:
    global _pool, _fut, _fut_key
    with _lock:
        _fut = None
        _fut_key = None
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=False)
            _pool = None


atexit.register(_shutdown_pool)


def run_query_timed(
    tokens: list[str],
    *,
    timeout: float = LIVE_QUERY_TIMEOUT,
    **kwargs: Any,
) -> tuple[dict | None, bool]:
    """
    Run run_query in a worker thread. Returns (payload, timed_out).

    On timeout, returns immediately with (None, True). The worker is left
    running; a later call with the same tokens reaps the result. A new query
    is not started while one is still in flight (max_workers=1).
    """
    from backend.resources import run_query

    key = _query_key(tokens, kwargs)

    with _lock:
        global _fut, _fut_key
        if _fut is not None and not _fut.done():
            return None, True
        if _fut is not None and _fut.done():
            stale = _fut
            same = _fut_key == key
            _fut = None
            _fut_key = None
            if same:
                try:
                    return stale.result(), False
                except Exception as exc:
                    return {
                        "ok": False,
                        "resource": "live",
                        "error": f"{type(exc).__name__}: {exc}",
                    }, False
        fut = _executor().submit(run_query, tokens, **kwargs)
        _fut = fut
        _fut_key = key

    try:
        payload = fut.result(timeout=timeout)
    except futures.TimeoutError:
        return None, True
    except Exception as exc:
        with _lock:
            if _fut is fut:
                _fut = None
                _fut_key = None
        return {
            "ok": False,
            "resource": "live",
            "error": f"{type(exc).__name__}: {exc}",
        }, False

    with _lock:
        if _fut is fut:
            _fut = None
            _fut_key = None
    return payload, False
