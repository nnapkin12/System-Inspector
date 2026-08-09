"""
SystemInspector local API.

This is the desktop "main process" equivalent:
  - Reads hardware / live metrics from the machine
  - Serves JSON on localhost only (free, no accounts, no cloud)

UI is static HTML/JS in ../frontend — open via this same server.
CLI (sysinspect / si) uses the same resource helpers without needing the server.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.collectors import get_inventory, get_vitals
from backend.resources import (
    CANONICAL,
    apply_fields,
    get_resource,
    list_commands_help,
    run_query,
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="SystemInspector",
    description="Local-only hardware inventory and live vitals (no cloud, no paid APIs).",
    version="0.2.0",
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


@app.get("/api/help", response_class=PlainTextResponse)
def api_help() -> str:
    return list_commands_help()


@app.get("/api/commands")
def api_commands() -> dict:
    return {
        "ok": True,
        "resources": list(CANONICAL),
        "cli": ["sysinspect", "si"],
        "examples": [
            "sysinspect gpu",
            "sysinspect cpu temp",
            "sysinspect gpu temp",
            "sysinspect temps",
            "sysinspect motherboard",
            "sysinspect status",
            "sysinspect watch gpu",
        ],
    }


@app.get("/api/query")
def api_query(
    q: str = Query(..., description="Space or + separated tokens, e.g. 'gpu temp' or 'cpu+gpu'"),
    include_pci: bool = False,
) -> dict:
    tokens = [t for t in q.replace("+", " ").split() if t]
    return run_query(tokens, include_pci=include_pci)


@app.get("/api/status")
def api_status() -> dict:
    return get_resource("status")


@app.get("/api/cpu")
def api_cpu(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("cpu"), fields)


@app.get("/api/gpu")
def api_gpu(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("gpu"), fields)


@app.get("/api/memory")
@app.get("/api/ram")
def api_memory(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("memory"), fields)


@app.get("/api/temps")
@app.get("/api/temp")
def api_temps(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("temps"), fields)


@app.get("/api/board")
@app.get("/api/motherboard")
def api_board(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("board"), fields)


@app.get("/api/os")
def api_os(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("os"), fields)


@app.get("/api/disk")
@app.get("/api/storage")
def api_disk(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("disk"), fields)


@app.get("/api/net")
@app.get("/api/network")
def api_net(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("net"), fields)


@app.get("/api/battery")
def api_battery(fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("battery"), fields)


@app.get("/api/scan")
def api_scan(include_pci: bool = False, fields: Optional[str] = None) -> dict:
    return _with_fields(get_resource("scan", include_pci=include_pci), fields)


@app.get("/api/all")
def api_all() -> dict:
    return get_resource("all")


def _with_fields(payload: dict, fields: Optional[str]) -> dict:
    if not fields:
        return payload
    field_set = {f.strip().lower() for f in fields.split(",") if f.strip()}
    if "temps" in field_set:
        field_set.discard("temps")
        field_set.add("temp")
    if "util" in field_set:
        field_set.discard("util")
        field_set.add("usage")
    return apply_fields(payload, field_set)


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
