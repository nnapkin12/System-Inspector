"""Light, time-aware damping for live *load* meters only.

Temps, VRAM, power, and RAM are never touched.

NVML already returns a short GPU-util window. A 30%→45% tick is often
real compositor noise. We only blend small moves, and we scale by the
refresh interval so `faster` does not over-smooth in wall-clock time.
A jump of 20 points or more snaps — that is a real load change.
"""

from __future__ import annotations

import math
from typing import Any

# Half-second memory: at the default 1s refresh this is almost the raw sample.
_DEFAULT_TAU = 0.45
_SNAP_DELTA = 20.0


class MetricSmoother:
    def __init__(self, tau: float = _DEFAULT_TAU) -> None:
        self.tau = max(0.15, float(tau))
        self._prev: dict[str, float] = {}

    def reset(self) -> None:
        self._prev.clear()

    def value(self, key: str, raw: Any, *, dt: float = 1.0) -> float | None:
        if raw is None:
            return None
        try:
            x = float(raw)
        except (TypeError, ValueError):
            return None
        prev = self._prev.get(key)
        if prev is None or abs(x - prev) >= _SNAP_DELTA:
            self._prev[key] = x
            return x
        step = max(0.05, float(dt))
        alpha = 1.0 - math.exp(-step / self.tau)
        alpha = min(0.92, max(0.25, alpha))
        sm = prev + alpha * (x - prev)
        self._prev[key] = sm
        return round(sm, 1)

    def apply_payload(self, payload: dict | None, *, dt: float = 1.0) -> dict | None:
        """Shallow-copy payload and damp load % only. Temps stay raw."""
        if not payload or not payload.get("ok"):
            return payload
        resource = payload.get("resource")
        if resource == "bundle":
            out = dict(payload)
            out["results"] = [
                self.apply_payload(part, dt=dt) or part for part in (payload.get("results") or [])
            ]
            return out
        data = payload.get("data")
        if not isinstance(data, dict):
            return payload
        out = dict(payload)
        if resource == "status":
            live = dict(data.get("live") or {})
            live["cpu_percent"] = self.value("status.cpu", live.get("cpu_percent"), dt=dt)
            live["gpu_percent"] = self.value("status.gpu", live.get("gpu_percent"), dt=dt)
            data = dict(data)
            data["live"] = live
            out["data"] = data
        elif resource == "cpu":
            data = dict(data)
            data["usage_percent"] = self.value("cpu", data.get("usage_percent"), dt=dt)
            out["data"] = data
        elif resource == "gpu":
            data = dict(data)
            devices = []
            for i, gpu in enumerate(data.get("devices") or []):
                row = dict(gpu)
                row["usage_percent"] = self.value(f"gpu{i}", row.get("usage_percent"), dt=dt)
                devices.append(row)
            data["devices"] = devices
            out["data"] = data
        return out
