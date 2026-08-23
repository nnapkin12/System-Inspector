from backend.tui import (
    _sev_style,
    format_status_board,
    format_watch_dashboard,
    load_si_logo,
    logo_header,
    meter,
    meter_block,
    temp_meter,
)


def test_load_si_logo_fallback_or_file():
    lines = load_si_logo()
    assert len(lines) >= 5
    assert any(line.strip() for line in lines)
    art = "\n".join(lines)
    assert "SYSTEM" in art
    assert "INSPECT" in art


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


def test_sev_style_is_green_yellow_red():
    from backend.tui import _BOLD, _GRN, _RED, _WHITE, _YEL

    assert _sev_style(20) == (_GRN,)
    assert _sev_style(40) == (_GRN,)
    assert _sev_style(60) == (_BOLD, _YEL)
    assert _sev_style(90) == (_BOLD, _RED)
    assert _WHITE not in _sev_style(40)
    assert _WHITE not in _sev_style(60)
    assert _sev_style(50, hot=True) == (_GRN,)
    assert _sev_style(70, hot=True) == (_BOLD, _YEL)
    assert _sev_style(90, hot=True) == (_BOLD, _RED)


def test_meter_colors_skip_white_mid():
    low = meter(30, width=10, color=True)
    mid = meter(60, width=10, color=True)
    high = meter(90, width=10, color=True)
    assert "\033[92m" in low
    assert "\033[97m" not in low
    assert "\033[93m" in mid
    assert "\033[97m" not in mid
    assert "\033[91m" in high


def test_temp_meter_uses_celsius_not_mapped_pct():
    # 70°C maps to ~60% bar fill; color must follow 70°C (yellow), not 60% load.
    out = temp_meter(70, width=10, color=True)
    assert "\033[93m" in out
    assert "70°C" in out


def test_status_board_fits_one_page(monkeypatch):
    monkeypatch.setattr("backend.tui.term_width", lambda: 80)
    monkeypatch.setattr("backend.tui.term_height", lambda: 30)
    from backend.tui import strip_ansi

    payload = {
        "ok": True,
        "resource": "status",
        "data": {
            "hostname": "box",
            "os": "TestOS",
            "cpu": "FakeCPU",
            "gpus": ["RTX"],
            "ram_gb": 16,
            "uptime_seconds": 120,
            "live": {
                "cpu_percent": 12,
                "cpu_temp_c": 48,
                "cpu_freq_mhz": 4200,
                "load_1m": 0.8,
                "gpu_percent": 35,
                "gpu_temp_c": 40,
                "gpu_power_w": 7.6,
                "gpu_clock_mhz": 915,
                "gpu_vram_used_mb": 1122,
                "gpu_vram_total_mb": 6141,
                "ram_percent": 41,
                "ram_used_gb": 6.2,
                "ram_total_gb": 14.8,
                "disk_read_mbs": 0.2,
                "disk_write_mbs": 0.0,
                "net_recv_mbs": 0.1,
                "net_sent_mbs": 0.0,
                "battery_percent": 82,
                "battery_plugged": True,
            },
        },
    }
    out = format_status_board(payload, color=False)
    lines = out.splitlines()
    body = strip_ansi(out)
    assert "CPU" in body and "12%" in body and "48°C" in body
    assert "GPU" in body and "35%" in body
    assert "VRAM" in body
    assert "NET" in body
    assert "disk" not in body.lower()
    assert "BAT" in body
    assert "TestOS" not in body
    assert "box" not in body.split("CPU")[0]
    bar_lines = [strip_ansi(ln) for ln in lines if "[" in ln]
    assert bar_lines
    assert all(len(ln) >= 40 for ln in bar_lines)
    for line in lines:
        assert len(strip_ansi(line)) <= 80
