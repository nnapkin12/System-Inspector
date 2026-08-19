from backend.live_loop import LiveState, _footer_line_count, _layout_frame, _visible_flash
from backend.tui import strip_ansi


def test_footer_stable_when_switching_query(monkeypatch):
    monkeypatch.setattr("backend.live_loop.term_height", lambda: 30)
    monkeypatch.setattr("backend.tui.term_height", lambda: 30)
    monkeypatch.setattr("backend.tui.term_width", lambda: 100)

    state = LiveState(tokens=["cpu"], interval=1.0, show_graph=False, show_logo=False)
    state.flash = "watching cpu"
    state.flash_until = 9999999999
    assert _visible_flash(state) == ""
    assert _footer_line_count(state) == 3

    state.flash = "faster · every 0.5s"
    assert _visible_flash(state) != ""
    assert _footer_line_count(state) == 4


def test_layout_pins_footer_and_keeps_prompt(monkeypatch):
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
        return "GPU\n" + ("X" * 120 + "\n") * 30

    board, chrome, chrome_row = _layout_frame(state, render_once, color=False)
    assert "›" in chrome
    assert "watching  gpu" in strip_ansi(chrome)
    assert chrome_row == 22  # 24 - 3 + 1
    assert board.count("\n") + 1 < chrome_row
    assert all(len(strip_ansi(ln)) <= 80 for ln in board.splitlines())


def test_short_board_still_pins_chrome_at_bottom(monkeypatch):
    monkeypatch.setattr("backend.live_loop.term_height", lambda: 24)
    monkeypatch.setattr("backend.tui.term_height", lambda: 24)
    monkeypatch.setattr("backend.tui.term_width", lambda: 80)

    state = LiveState(tokens=["gpu"], interval=1.0, show_graph=False, show_logo=False)
    state.payload = {
        "ok": True,
        "resource": "gpu",
        "data": {"devices": [{"name": "GPU", "usage_percent": 50}]},
    }

    def render_once(payload, *, live=False):
        return "GPU\n50%"

    _board, chrome, chrome_row = _layout_frame(state, render_once, color=False)
    assert chrome_row == 22
    assert "›" in chrome


def test_paint_board_does_not_write_footer_row(monkeypatch):
    import io
    import sys

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    from backend.tui import paint_board_region

    paint_board_region("A\nB", 10)
    out = buf.getvalue()
    assert "\033[1;1H" in out
    assert "\033[2;1H" in out
    assert "\033[10;1H" not in out
    assert "\033[K" in out
