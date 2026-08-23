from backend.graphs import (
    BrailleCanvas,
    LiveHistory,
    map_y,
    render_graph_board,
    series_from_payload,
)
from backend.tui import strip_ansi


def test_braille_line_sets_dots():
    canvas = BrailleCanvas(4, 2)
    canvas.line(0, 0, 7, 7)
    text = "".join(canvas.rows_text())
    assert any("\u2801" <= ch <= "\u28ff" for ch in text)


def test_map_y_uses_fixed_percent_scale():
    assert map_y(0, 0, 100, 40) == 0
    assert map_y(100, 0, 100, 40) == 39
    assert map_y(2, 0, 100, 40) < map_y(50, 0, 100, 40)
    # 2% must stay near the floor — not auto-zoomed to mid-plot
    assert map_y(2, 0, 100, 40) <= 2


def test_graph_board_has_axis_and_current_value():
    history = LiveHistory(maxlen=20)
    for v in (10, 20, 40, 42):
        history.push([("CPU %", float(v), "pct")])
    board = render_graph_board(
        history, interval=1.0, color=False, watching="cpu", width=80, height=20
    )
    plain = strip_ansi(board)
    assert "CPU %" in plain
    assert "42%" in plain
    assert "┤" in plain
    assert "now" in plain
    assert "[" not in plain
    assert any("\u2800" <= ch <= "\u28ff" for ch in plain)


def test_graph_only_board_skips_bar_dashboard(monkeypatch):
    from backend.live_loop import LiveState, _layout_frame

    monkeypatch.setattr("backend.live_loop.term_height", lambda: 30)
    monkeypatch.setattr("backend.live_loop.term_width", lambda: 100)
    monkeypatch.setattr("backend.tui.term_height", lambda: 30)
    monkeypatch.setattr("backend.tui.term_width", lambda: 100)
    monkeypatch.setattr("backend.graphs.term_height", lambda: 30)
    monkeypatch.setattr("backend.graphs.term_width", lambda: 100)

    state = LiveState(
        tokens=["cpu"],
        interval=1.0,
        show_graph=True,
        graph_only=True,
        show_logo=False,
    )
    for v in (12, 18, 25):
        state.history.push([("CPU %", float(v), "pct"), ("CPU °C", 55.0, "temp")])
    state.payload = {
        "ok": True,
        "resource": "cpu",
        "data": {"usage_percent": 25, "temp_c": 55},
    }

    def render_once(payload, *, live=False):
        return "SHOULD_NOT_SEE_BARS\n    [████░░░░]  25%"

    board, chrome, _row = _layout_frame(state, render_once, color=False)
    plain = strip_ansi(board)
    assert "SHOULD_NOT_SEE_BARS" not in plain
    assert "[█" not in plain
    assert "CPU %" in plain
    assert "graph" in strip_ansi(chrome)


def test_series_from_status_includes_vram_and_net():
    points = series_from_payload(
        {
            "ok": True,
            "resource": "status",
            "data": {
                "live": {
                    "cpu_percent": 10,
                    "cpu_temp_c": 45,
                    "gpu_percent": 30,
                    "gpu_temp_c": 60,
                    "ram_percent": 40,
                    "gpu_vram_used_mb": 2048,
                    "gpu_vram_total_mb": 8192,
                    "net_recv_mbs": 1.5,
                    "net_sent_mbs": 0.2,
                }
            },
        }
    )
    names = {n for n, _v, _u in points}
    assert "CPU %" in names
    assert "VRAM %" in names
    assert "Net ↓" in names


def test_cli_graph_enters_graph_only(monkeypatch):
    import sysinspect

    called: dict = {}

    def fake_live(**kwargs):
        called.update(kwargs)
        return 0

    monkeypatch.setattr(sysinspect, "run_interactive_live", fake_live)
    monkeypatch.setattr(sysinspect.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sysinspect.sys.stdout, "isatty", lambda: True)

    assert sysinspect.main(["graph", "cpu"]) == 0
    assert called["show_graph"] is True
    assert called["tokens"] == ["cpu"]

    called.clear()
    assert sysinspect.main(["gpu", "temp", "--graphs"]) == 0
    assert called["show_graph"] is True
    assert called["tokens"] == ["gpu", "temp"]

    called.clear()
    assert sysinspect.main(["cpu"]) == 0
    assert called["show_graph"] is False
    assert called["tokens"] == ["cpu"]


def test_regular_status_layout_still_uses_bars(monkeypatch):
    from backend.live_loop import LiveState, _layout_frame

    monkeypatch.setattr("backend.live_loop.term_height", lambda: 24)
    monkeypatch.setattr("backend.tui.term_height", lambda: 24)
    monkeypatch.setattr("backend.tui.term_width", lambda: 80)

    state = LiveState(tokens=["gpu"], interval=1.0, show_graph=False, show_logo=False)
    state.payload = {
        "ok": True,
        "resource": "gpu",
        "data": {"devices": [{"name": "GPU", "usage_percent": 50, "temp_c": 60}]},
    }

    def render_once(payload, *, live=False):
        return "GPU\n    [████████░░░░]  50%"

    board, chrome, _row = _layout_frame(state, render_once, color=False)
    assert "50%" in strip_ansi(board)
    assert "graph" not in strip_ansi(chrome)
