import json
import socket
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.gui import (
    WEB_DIR,
    GuiState,
    bind_server,
    is_gui_command,
    run_gui,
    start_message,
)
from backend.query import parse_query


@contextmanager
def running_server(state=None, port=0):
    httpd, remapped = bind_server("127.0.0.1", port, state or GuiState())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, remapped
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _url(httpd, path: str) -> str:
    host, port = httpd.server_address[:2]
    return f"http://{host}:{port}{path}"


def _get(httpd, path: str, *, timeout: float = 5):
    req = Request(_url(httpd, path), method="GET")
    return urlopen(req, timeout=timeout)


def _get_json(httpd, path: str) -> dict:
    with _get(httpd, path) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_gui_is_a_mode_not_a_resource():
    assert is_gui_command(["gui"]) is True
    assert is_gui_command(["web"]) is True
    assert is_gui_command(["GUI"]) is True
    assert is_gui_command(["gui", "web"]) is True
    assert is_gui_command(["gui", "status"]) is False
    assert is_gui_command(["gpu"]) is False
    assert is_gui_command([]) is False
    resources, _fields, unknown = parse_query(["gui"])
    assert resources == []
    assert unknown == ["gui"]


def test_start_message_is_copy_paste():
    text = start_message("http://127.0.0.1:8000")
    assert "copy this link" in text.lower()
    assert "http://127.0.0.1:8000" in text
    assert "Ctrl+C" in text
    assert start_message("http://127.0.0.1:8001", remapped=True).startswith("Port 8000 was busy")
    assert start_message(
        "http://127.0.0.1:9001", remapped=True, wanted=9000
    ).startswith("Port 9000 was busy")


def test_bind_localhost_only():
    with running_server() as (httpd, remapped):
        assert remapped is False
        assert httpd.server_address[0] == "127.0.0.1"
        assert httpd.server_address[1] > 0


def test_bind_skips_busy_port():
    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    port = busy.getsockname()[1]
    try:
        with running_server(port=port) as (httpd, remapped):
            assert remapped is True
            assert httpd.server_address[1] != port
    finally:
        busy.close()


def test_index_and_assets_served():
    assert (WEB_DIR / "index.html").is_file()
    with running_server() as (httpd, _):
        with _get(httpd, "/") as resp:
            html = resp.read().decode("utf-8")
            assert resp.headers.get("Content-Type", "").startswith("text/html")
            assert "System Inspector" in html
            assert "Content-Security-Policy" in resp.headers
        with _get(httpd, "/style.css") as resp:
            assert "text/css" in resp.headers.get("Content-Type", "")
            css = resp.read().decode("utf-8")
            assert "#2e3440" in css
        with _get(httpd, "/app.js") as resp:
            js = resp.read().decode("utf-8")
            assert "/api/query" in js


def test_path_traversal_rejected():
    with running_server() as (httpd, _):
        try:
            _get(httpd, "/../../backend/gui.py")
            raise AssertionError("expected 404")
        except HTTPError as err:
            assert err.code == 404


def test_api_query_uses_run_query():
    seen: list[list[str]] = []

    def fake(tokens, **kwargs):
        seen.append(list(tokens))
        return {"ok": True, "resource": "cpu", "data": {"usage_percent": 12}}

    state = GuiState(run_query=fake)
    with running_server(state) as (httpd, _):
        body = _get_json(httpd, "/api/query?q=cpu")
    assert seen == [["cpu"]]
    assert body["ok"] is True
    assert body["data"]["usage_percent"] == 12


def test_api_unknown_and_empty():
    with running_server() as (httpd, _):
        try:
            _get(httpd, "/api/query?q=not-a-command")
            raise AssertionError("expected 400")
        except HTTPError as err:
            assert err.code == 400
            payload = json.loads(err.read().decode("utf-8"))
            assert payload["ok"] is False
            assert "Unknown" in payload["error"]
        try:
            _get(httpd, "/api/query")
            raise AssertionError("expected 400")
        except HTTPError as err:
            assert err.code == 400


def test_api_redact():
    def fake(tokens, **kwargs):
        return {"ok": True, "resource": "board", "data": {"serial": "ABC123456789"}}

    state = GuiState(run_query=fake, redact=True)
    with running_server(state) as (httpd, _):
        body = _get_json(httpd, "/api/query?q=motherboard")
    assert body["data"]["serial"] == "****6789"


def test_api_meta():
    with running_server() as (httpd, _):
        body = _get_json(httpd, "/api/meta")
    assert body["ok"] is True
    assert body["name"] == "System Inspector"
    assert "version" in body


def test_run_gui_prints_link_then_stops(monkeypatch):
    lines: list[str] = []

    def boom(self):
        raise KeyboardInterrupt

    monkeypatch.setattr("backend.gui.GuiHTTPServer.serve_forever", boom)
    code = run_gui(port=0, print_fn=lines.append)
    assert code == 0
    text = "\n".join(lines)
    assert "copy this link" in text.lower()
    assert "http://127.0.0.1:" in text
    assert "Stopped." in text


def test_run_gui_json_mode(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(
        "backend.gui.GuiHTTPServer.serve_forever",
        lambda self: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    code = run_gui(port=0, json_mode=True, print_fn=lines.append)
    assert code == 0
    payload = json.loads(lines[0])
    assert payload["ok"] is True
    assert payload["url"].startswith("http://127.0.0.1:")


def test_cli_gui_dispatch(monkeypatch):
    import sysinspect

    called: dict = {}

    def fake(**kwargs):
        called.update(kwargs)
        return 0

    monkeypatch.setattr(sysinspect, "run_gui", fake)
    assert sysinspect.main(["gui"]) == 0
    assert called["port"] == 8000
    assert called["json_mode"] is False

    called.clear()
    assert sysinspect.main(["web", "--port", "9001", "--redact"]) == 0
    assert called["port"] == 9001
    assert called["redact"] is True


def test_cli_gui_rejects_extra_words():
    import sysinspect

    assert sysinspect.main(["gui", "status"]) == 2


def test_help_mentions_gui_quietly():
    from backend.help_text import FULL_HELP

    assert "si gui" in FULL_HELP
    assert FULL_HELP.index("si gpu") < FULL_HELP.index("si gui")


def test_system_page_tokens_do_not_collapse_to_os_version():
    resources, fields, unknown = parse_query(["os", "board", "display", "uptime"])
    assert resources == ["os", "board", "display", "uptime"]
    assert "version" not in fields
    assert unknown == []
