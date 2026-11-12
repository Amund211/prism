from prism.overlay.server import Server
from prism.overlay.state import OverlayState
from prism.overlay.tabshot.capture import Monitor
from prism.overlay.tabshot.metadata import (
    CaptureInfo,
    PrismWindow,
    build_metadata,
    state_metadata,
)
from prism.overlay.tabshot.window import GameWindow

MONITORS = (Monitor(-100, 0, 300, 50), Monitor(-100, 0, 100, 50))


def test_state_metadata() -> None:
    state = OverlayState(
        party_members=frozenset(("b", "a")),
        lobby_players=frozenset(("c", "a")),
        alive_players=frozenset(("a",)),
        last_game_start=10.0,
        own_username="a",
        server=Server.from_host("mc.hypixel.net"),
    )
    assert state_metadata(state, now=12.5) == {
        "own_username": "a",
        "party": ["a", "b"],
        "lobby": ["a", "c"],
        "alive": ["a"],
        "in_queue": False,
        "out_of_sync": False,
        "since_game_start_s": 2.5,
        "bedwars_duel": None,
        "server": {"host": "mc.hypixel.net", "kind": "hypixel"},
    }

    empty = state_metadata(OverlayState(), now=1.0)
    assert empty["since_game_start_s"] is None
    assert empty["server"] is None


def test_build_metadata() -> None:
    window = GameWindow(
        rect=(10, 20, 30, 40),
        pid=1,
        exe="java",
        window_class="LWJGL",
        title="Minecraft",
        foreground=True,
        dpi=120,
    )
    metadata = build_metadata(
        state=OverlayState(),
        now=1.0,
        monitors=MONITORS,
        windows=[window],
        prism=PrismWindow(rect=(-50, 5, 10, 10), shown=True, alpha=0.8),
        captures=[
            CaptureInfo("x.png", 30, 31.04, 9.96),
            CaptureInfo("y.png", 300, 301.0, 9.0, {"a": "red"}, 123.45),
        ],
        known=["a", "b"],
        pressed_at_unix=123.0,
        held_ms=None,
        thread_dpi_aware=False,
    )
    assert metadata["version"] == 2
    assert metadata["known"] == ["a", "b"]
    assert metadata["monitors"][1] == {
        "rect": [0, 0, 100, 50],
        "screen_rect": [-100, 0, 100, 50],
    }
    assert metadata["windows"][0]["rect"] == [110, 20, 30, 40]
    assert metadata["windows"][0]["screen_rect"] == [10, 20, 30, 40]
    assert metadata["windows"][0]["dpi"] == 120
    assert metadata["prism"] == {
        "rect": [50, 5, 10, 10],
        "screen_rect": [-50, 5, 10, 10],
        "shown": True,
        "alpha": 0.8,
    }
    assert metadata["captures"] == [
        {
            "file": "x.png",
            "delay_ms": 30,
            "actual_delay_ms": 31.0,
            "grab_ms": 10.0,
            "teams": None,
            "read_ms": None,
        },
        {
            "file": "y.png",
            "delay_ms": 300,
            "actual_delay_ms": 301.0,
            "grab_ms": 9.0,
            "teams": {"a": "red"},
            "read_ms": 123.5,
        },
    ]
    assert metadata["tab"] == {"pressed_at_unix": 123.0, "held_ms": None}

    bare = build_metadata(
        state=OverlayState(),
        now=1.0,
        monitors=MONITORS,
        windows=None,
        prism=None,
        captures=[],
        known=[],
        pressed_at_unix=123.0,
        held_ms=5.0,
        thread_dpi_aware=True,
    )
    assert bare["windows"] is None
    assert bare["prism"] is None
