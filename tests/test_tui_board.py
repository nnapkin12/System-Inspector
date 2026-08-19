from backend.tui import format_watch_dashboard, logo_header, meter_block, load_si_logo


def test_load_si_logo_fallback_or_file():
    lines = load_si_logo()
    assert len(lines) >= 5
    assert any(line.strip() for line in lines)


def test_logo_header_includes_title_and_watching():
    out = logo_header(watching="gpu temp", color=False)
    assert "SYSTEM INSPECTOR" in out
    assert "gpu temp" in out


def test_meter_block_has_number_and_bar():
    lines = meter_block(42, width=20, color=False, rows=2)
    assert any("42%" in line for line in lines)
    assert sum(1 for line in lines if "[" in line) == 2


def test_meter_block_fits_narrow_terminal(monkeypatch):
    monkeypatch.setattr("backend.tui.term_width", lambda: 40)
    from backend.tui import default_bar_width, strip_ansi

    width = default_bar_width()
    lines = meter_block(40, width=width, color=False, rows=1)
    for line in lines:
        assert len(strip_ansi(line)) <= 40


def test_watch_dashboard_lines_fit_terminal(monkeypatch):
    monkeypatch.setattr("backend.tui.term_width", lambda: 80)
    monkeypatch.setattr("backend.tui.term_height", lambda: 24)
    from backend.tui import strip_ansi

    payload = {
        "ok": True,
        "resource": "cpu",
        "data": {"usage_percent": 10, "temp_c": 72, "freq_current_mhz": 4200},
    }
    out = format_watch_dashboard(payload, color=False)
    for line in out.splitlines():
        assert len(strip_ansi(line)) <= 80


def test_watch_dashboard_shows_big_temp():
    payload = {
        "ok": True,
        "resource": "cpu",
        "data": {"usage_percent": 10, "temp_c": 72, "freq_current_mhz": 4200},
    }
    out = format_watch_dashboard(payload, color=False)
    assert "CPU" in out
    assert "10%" in out
    assert "72°C" in out
