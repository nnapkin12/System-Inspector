"""
Optional localhost web UI. Started only by `si gui` / `si web`.

Stdlib http.server — no extra dependency. Binds 127.0.0.1.
Pages call the same run_query() path as the CLI; this file does not talk to sysfs.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from backend.live_query import InventoryCache
from backend.query import parse_query, vitals_needs_for_tokens
from backend.redact import redact_payload
from backend.resources import run_query as _run_query
from backend.version import NAME, VERSION

GUI_WORDS = frozenset({"gui", "web"})
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PORT_TRIES = 20
MAX_QUERY_CHARS = 200
MAX_TOKENS = 16
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

_MIME = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".woff2": "font/woff2",
}

_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'"
)

QueryFn = Callable[..., dict]


def is_gui_command(tokens: list[str]) -> bool:
    """True when the user asked to start the optional web UI."""
    words = [t.strip().lower() for t in tokens if t and t.strip()]
    return bool(words) and all(w in GUI_WORDS for w in words)


def start_message(url: str, *, remapped: bool = False, wanted: int | None = None) -> str:
    lines = [
        "To load the web interface, copy this link and paste it in your browser:",
        "",
        f"  {url}",
        "",
        "Ctrl+C stops the server.",
    ]
    if remapped:
        used = url.rsplit(":", 1)[-1]
        lines.insert(0, f"Port {wanted or DEFAULT_PORT} was busy — using {used}.")
        lines.insert(1, "")
    return "\n".join(lines)


def public_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


@dataclass
class GuiState:
    redact: bool = False
    verbose: bool = False
    include_pci: bool = False
    cache: InventoryCache = field(default_factory=InventoryCache)
    lock: threading.Lock = field(default_factory=threading.Lock)
    run_query: QueryFn = field(default=_run_query)


class GuiHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], state: GuiState) -> None:
        self.state = state
        super().__init__(addr, GuiHandler)


class GuiHandler(BaseHTTPRequestHandler):
    server_version = f"si-gui/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Polling would spam the terminal; the start message is the UX.
        return

    @property
    def state(self) -> GuiState:
        return self.server.state  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path or "/")
        if path == "/api/query":
            self._api_query(parse_qs(parsed.query))
            return
        if path == "/api/meta":
            self._api_meta()
            return
        self._static(path)

    def do_HEAD(self) -> None:
        self.do_GET()

    def _api_meta(self) -> None:
        host, port = self.server.server_address[:2]
        body = {
            "ok": True,
            "name": NAME,
            "version": VERSION,
            "host": host,
            "port": port,
            "cli": "si · sysinspect",
        }
        self._json(200, body)

    def _api_query(self, qs: dict[str, list[str]]) -> None:
        raw = (qs.get("q") or [""])[0]
        if len(raw) > MAX_QUERY_CHARS:
            self._json(400, {"ok": False, "error": "Query too long"})
            return
        tokens = [t for t in raw.split() if t]
        if not tokens:
            self._json(400, {"ok": False, "error": "Missing q (example: q=status)"})
            return
        if len(tokens) > MAX_TOKENS:
            self._json(400, {"ok": False, "error": "Too many tokens"})
            return
        _resources, _fields, unknown = parse_query(tokens)
        if unknown and not _resources:
            self._json(
                400,
                {
                    "ok": False,
                    "error": f"Unknown: {', '.join(unknown)}",
                    "hint": "Same words as the CLI: gpu · cpu · status · net …",
                },
            )
            return
        try:
            payload = execute_query(self.state, tokens)
        except Exception as exc:
            self._json(
                500,
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            )
            return
        self._json(200, payload)

    def _static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        target = _safe_web_file(rel)
        if target is None:
            self._json(404, {"ok": False, "error": "Not found"})
            return
        data = target.read_bytes()
        mime = _MIME.get(target.suffix.lower(), "application/octet-stream")
        self._bytes(200, data, mime, cache="no-cache")

    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self._bytes(code, data, "application/json; charset=utf-8", cache="no-store")

    def _bytes(self, code: int, data: bytes, content_type: str, *, cache: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", _CSP)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


def _safe_web_file(rel: str) -> Path | None:
    root = WEB_DIR.resolve()
    if not rel or rel.endswith("/"):
        rel = rel + "index.html" if rel else "index.html"
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def execute_query(state: GuiState, tokens: list[str]) -> dict:
    """One collector pass, same Snapshot/cache rules as live mode."""
    with state.lock:
        snap = state.cache.make_snapshot(
            include_pci=state.include_pci,
            verbose=state.verbose,
            vitals_needs=vitals_needs_for_tokens(tokens),
        )
        payload = state.run_query(
            tokens,
            snap=snap,
            include_pci=state.include_pci,
            verbose=state.verbose,
        )
        state.cache.remember(snap)
        if state.redact:
            payload = redact_payload(payload)
        return payload


def bind_server(
    host: str,
    port: int,
    state: GuiState | None = None,
) -> tuple[GuiHTTPServer, bool]:
    """
    Bind localhost. If `port` is taken, try the next few.
    Returns (server, remapped).
    """
    state = state or GuiState()
    if port == 0:
        return GuiHTTPServer((host, 0), state), False
    last_err: OSError | None = None
    for candidate in range(port, port + PORT_TRIES):
        try:
            httpd = GuiHTTPServer((host, candidate), state)
            return httpd, candidate != port
        except OSError as exc:
            last_err = exc
    raise OSError(f"Could not bind {host}:{port}–{port + PORT_TRIES - 1}: {last_err}")


def run_gui(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    redact: bool = False,
    verbose: bool = False,
    include_pci: bool = False,
    json_mode: bool = False,
    print_fn: Callable[[str], None] | None = None,
) -> int:
    """Print the copy-paste URL and serve until Ctrl+C. Returns a process exit code."""
    emit = print_fn or (lambda s: print(s, flush=True))
    state = GuiState(redact=redact, verbose=verbose, include_pci=include_pci)
    try:
        httpd, remapped = bind_server(host, port, state)
    except OSError as exc:
        emit(f"Could not start the web UI: {exc}")
        return 1
    bound_host, bound_port = httpd.server_address[:2]
    url = public_url(str(bound_host), int(bound_port))
    if json_mode:
        emit(
            json.dumps(
                {
                    "ok": True,
                    "url": url,
                    "host": bound_host,
                    "port": bound_port,
                    "remapped": remapped,
                },
                indent=2,
            )
        )
    else:
        emit(start_message(url, remapped=remapped, wanted=port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        emit("\nStopped.")
        return 0
    finally:
        httpd.server_close()
    return 0
