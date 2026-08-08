"""
System Inspector desktop shell.

Starts the local API on 127.0.0.1, then opens a native window (pywebview).
If a desktop webview is unavailable, falls back to your default browser.
Closing the window stops the server.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "127.0.0.1"
PORT = 8787
URL = f"http://{HOST}:{PORT}"


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) != 0


def _wait_ready(timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _run_server() -> None:
    import uvicorn

    config = uvicorn.Config(
        "backend.main:app",
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    # Stash for shutdown
    app_state["server"] = server
    server.run()


app_state: dict = {}


def main() -> int:
    if not _port_free(HOST, PORT):
        # Already running — just open UI
        print(f"System Inspector already listening on {URL}")
        _open_ui(reuse=True)
        return 0

    thread = threading.Thread(target=_run_server, name="si-server", daemon=True)
    thread.start()

    if not _wait_ready():
        print("Failed to start local server on port 8787.", file=sys.stderr)
        return 1

    print(f"System Inspector → {URL}")
    _open_ui(reuse=False)

    # When window closes, stop uvicorn
    server = app_state.get("server")
    if server is not None:
        server.should_exit = True
    thread.join(timeout=3.0)
    return 0


def _open_ui(*, reuse: bool) -> None:
    logo = ROOT / "frontend" / "assets" / "logo.png"
    try:
        import webview

        window = webview.create_window(
            "System Inspector",
            URL,
            width=1280,
            height=860,
            min_size=(900, 640),
            background_color="#0a0809",
            text_select=True,
        )
        # optional icon — platform dependent
        if logo.is_file():
            try:
                window.set_icon(str(logo))  # type: ignore[attr-defined]
            except Exception:
                pass
        webview.start()
        return
    except Exception as exc:
        print(f"Native window unavailable ({exc}); opening browser instead.")
        webbrowser.open(URL)
        if reuse:
            return
        print("Press Ctrl+C to stop the backend.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
