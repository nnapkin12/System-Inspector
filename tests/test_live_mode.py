from backend.live_loop import normalize_live_input
from backend.live_mode import query_is_liveable, should_enter_live


def test_gpu_is_liveable():
    assert query_is_liveable(["gpu"]) is True
    assert query_is_liveable(["cpu", "temps"]) is True
    assert query_is_liveable(["status"]) is True
    assert query_is_liveable(["net"]) is True


def test_gui_words_are_not_liveable():
    assert query_is_liveable(["gui"]) is False
    assert query_is_liveable(["web"]) is False
    assert query_is_liveable(["os"]) is False
    assert query_is_liveable(["kernel"]) is False
    assert query_is_liveable(["motherboard"]) is False
    assert query_is_liveable(["scan"]) is False
    assert query_is_liveable(["version"]) is False
    assert query_is_liveable(["uptime"]) is False
    assert query_is_liveable(["display"]) is False
    assert query_is_liveable(["monitor"]) is False


def test_net_slices_are_snapshots():
    assert query_is_liveable(["net", "public"]) is False
    assert query_is_liveable(["net", "connections"]) is False
    assert query_is_liveable(["net", "listen"]) is False
    assert query_is_liveable(["net", "ping"]) is False


def test_mixed_cpu_os_is_snapshot():
    assert query_is_liveable(["cpu", "os"]) is False


def test_should_enter_live_tty_gpu():
    assert should_enter_live(
        ["gpu"], stdin_tty=True, stdout_tty=True
    ) is True


def test_should_not_enter_live_when_once_or_json_or_plain():
    kwargs = dict(stdin_tty=True, stdout_tty=True)
    assert should_enter_live(["gpu"], once=True, **kwargs) is False
    assert should_enter_live(["gpu"], json_mode=True, **kwargs) is False
    assert should_enter_live(["gpu"], plain=True, **kwargs) is False


def test_force_live_overrides_os_and_json():
    assert should_enter_live(
        ["os"], force_live=True, stdin_tty=True, stdout_tty=True
    ) is True
    assert should_enter_live(
        ["gpu"], force_live=True, json_mode=True, stdin_tty=False, stdout_tty=False
    ) is True


def test_non_tty_is_snapshot_unless_forced():
    assert should_enter_live(
        ["gpu"], stdin_tty=False, stdout_tty=True
    ) is False


def test_normalize_rejects_snapshot_words():
    tokens, flash = normalize_live_input(["os"])
    assert tokens is None
    assert "snapshot" in flash
    assert "si os" in flash


def test_normalize_accepts_gpu():
    tokens, flash = normalize_live_input(["gpu", "temps"])
    assert tokens == ["gpu", "temps"]
    assert "watching" in flash


def test_normalize_graph_alone_is_meta():
    tokens, flash = normalize_live_input(["graph"])
    assert tokens is None
    assert flash == "__graph__"
    tokens, flash = normalize_live_input(["graphs"])
    assert tokens is None
    assert flash == "__graph__"


def test_normalize_graph_cpu_switches_query():
    tokens, flash = normalize_live_input(["graph", "cpu", "gpu"])
    assert tokens == ["cpu", "gpu"]
    assert flash == "__graph__"


def test_normalize_bars_is_meta():
    tokens, flash = normalize_live_input(["bars"])
    assert tokens is None
    assert flash == "__bars__"
