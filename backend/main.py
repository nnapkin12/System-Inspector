"""
SystemInspector local API.

This is the desktop "main process" equivalent:
  - Reads hardware / live metrics from the machine
  - Serves JSON on localhost only (free, no accounts, no cloud)

UI is static HTML/JS in ../frontend — open via this same server.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.collectors import get_inventory, get_vitals

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="SystemInspector",
    description="Local-only hardware inventory and live vitals (no cloud, no paid APIs).",
    version="0.1.0",
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "SystemInspector", "bind": "127.0.0.1 only"}


@app.get("/api/inventory")
def inventory(include_pci: bool = True) -> dict:
    """Full hardware/OS discovery snapshot."""
    return get_inventory(include_pci=include_pci)


@app.get("/api/vitals")
def vitals() -> dict:
    """One-shot live metrics (CPU/GPU/RAM/temps/etc.)."""
    return get_vitals()


@app.websocket("/ws/vitals")
async def vitals_ws(websocket: WebSocket) -> None:
    """Push vitals about once per second."""
    await websocket.accept()
    try:
        while True:
            payload = get_vitals()
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
