"""Wall-clock timeout wrapper for live-mode queries."""

from __future__ import annotations

import atexit
import threading
import time
from concurrent import futures
from typing import Any

from backend import resources as resources_mod
from backend.collectors.vitals import VITALS_ALL
from backend.query import vitals_needs_for_tokens
from backend.snapshot import Snapshot

LIVE_QUERY_TIMEOUT = 2.5
INVENTORY_TTL = 30.0

_lock = threading.Lock()
_pool: futures.ThreadPoolExecutor | None = None
_fut: futures.Future | None = None
_fut_key: tuple | None = None
_fut_started: float = 0.0


class InventoryCache:
    """Reuse lspci/DMI inventory across live ticks. Vitals always refresh."""

    def __init__(self, ttl: float = INVENTORY_TTL) -> None:
        self.ttl = ttl
        self._data: dict | None = None
        self._at: float = 0.0
        self._pci: bool = False

    def make_snapshot(
        self,
        *,
        include_pci: bool = False,
        verbose: bool = False,
        vitals_needs: frozenset[str] | None = None,
    ) -> Snapshot:
        snap = Snapshot(
            include_pci=include_pci,
            verbose=verbose,
            vitals_needs=vitals_needs or VITALS_ALL,
        )
        now = time.monotonic()
        if (
            self._data is not None
            and self._pci == include_pci
            and (now - self._at) < self.ttl
        ):
            snap.reuse_inventory(self._data)
        return snap

    def remember(self, snap: Snapshot) -> None:
        data = snap.peek_inventory()
        if data is not None:
            self._data = data
            self._at = time.monotonic()
            self._pci = snap.include_pci


def _executor() -> futures.ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="si-live")
    return _pool


def _query_key(tokens: list[str], kwargs: dict[str, Any]) -> tuple:
    return (tuple(tokens), tuple(sorted((k, repr(v)) for k, v in kwargs.items())))


def reset_for_tests() -> None:
    """Drop in-flight state. Test-only."""
    global _pool, _fut, _fut_key, _fut_started
    with _lock:
        _fut = None
        _fut_key = None
        _fut_started = 0.0
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=False)
            _pool = None


def _shutdown_pool() -> None:
    global _pool, _fut, _fut_key, _fut_started
    with _lock:
        _fut = None
        _fut_key = None
        _fut_started = 0.0
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=False)
            _pool = None


atexit.register(_shutdown_pool)


def _submit_query(
    tokens: list[str],
    *,
    cache: InventoryCache | None,
    kwargs: dict[str, Any],
) -> None:
    """Start a worker if none is running."""
    global _fut, _fut_key, _fut_started
    key = _query_key(tokens, kwargs)
    needs = vitals_needs_for_tokens(tokens)

    def _work() -> dict:
        snap = None
        if cache is not None:
            snap = cache.make_snapshot(
                include_pci=bool(kwargs.get("include_pci", False)),
                verbose=bool(kwargs.get("verbose", False)),
                vitals_needs=needs,
            )
        result = resources_mod.run_query(tokens, snap=snap, **kwargs)
        if cache is not None and snap is not None:
            cache.remember(snap)
        return result

    with _lock:
        if _fut is not None and not _fut.done():
            return
        if _fut is not None and _fut.done():
            _fut = None
            _fut_key = None
        fut = _executor().submit(_work)
        _fut = fut
        _fut_key = key
        _fut_started = time.monotonic()


def _reap_done(*, key: tuple) -> tuple[dict | None, bool] | None:
    """If the in-flight worker finished, return (payload, timed_out). Else None."""
    global _fut, _fut_key, _fut_started
    with _lock:
        if _fut is None or not _fut.done():
            return None
        fut = _fut
        same = _fut_key == key
        _fut = None
        _fut_key = None
        _fut_started = 0.0
    if not same:
        try:
            fut.result(timeout=0)
        except Exception:
            pass
        return None
    try:
        return fut.result(timeout=0), False
    except Exception as exc:
        return {
            "ok": False,
            "resource": "live",
            "error": f"{type(exc).__name__}: {exc}",
        }, False


def poll_query_timed(
    tokens: list[str],
    *,
    timeout: float = LIVE_QUERY_TIMEOUT,
    cache: InventoryCache | None = None,
    **kwargs: Any,
) -> tuple[dict | None, bool, bool]:
    """
    Non-blocking live fetch. Returns (payload, timed_out, pending).

    *pending* True means a worker is still collecting — caller should keep
    reading keystrokes instead of blocking.
    """
    key = _query_key(tokens, kwargs)
    reaped = _reap_done(key=key)
    if reaped is not None:
        return reaped[0], reaped[1], False

    with _lock:
        in_flight = _fut is not None and not _fut.done()
        stale_key = in_flight and _fut_key != key

    if stale_key:
        if time.monotonic() - _fut_started >= timeout:
            return None, True, True
        return None, False, True

    if in_flight:
        if time.monotonic() - _fut_started >= timeout:
            return None, True, True
        return None, False, True

    _submit_query(tokens, cache=cache, kwargs=kwargs)
    return None, False, True


def run_query_timed(
    tokens: list[str],
    *,
    timeout: float = LIVE_QUERY_TIMEOUT,
    cache: InventoryCache | None = None,
    **kwargs: Any,
) -> tuple[dict | None, bool]:
    """
    Run run_query in a worker thread. Returns (payload, timed_out).

    On timeout, returns immediately with (None, True). The worker is left
    running; a later call with the same tokens reaps the result. A new query
    is not started while one is still in flight (max_workers=1).

    Optional InventoryCache skips repeating lspci/DMI on every tick.
    """
    payload, timed_out, pending = poll_query_timed(
        tokens, timeout=timeout, cache=cache, **kwargs
    )
    if not pending:
        return payload, timed_out
    # Blocking path for piped/script callers that expect to wait once.
    global _fut, _fut_key, _fut_started
    with _lock:
        fut = _fut
    if fut is None:
        return payload, timed_out
    try:
        payload = fut.result(timeout=timeout)
    except futures.TimeoutError:
        return None, True
    except Exception as exc:
        with _lock:
            if _fut is fut:
                _fut = None
                _fut_key = None
                _fut_started = 0.0
        return {
            "ok": False,
            "resource": "live",
            "error": f"{type(exc).__name__}: {exc}",
        }, False
    with _lock:
        if _fut is fut:
            _fut = None
            _fut_key = None
            _fut_started = 0.0
    return payload, False
