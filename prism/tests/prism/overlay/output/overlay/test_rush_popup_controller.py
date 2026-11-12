from prism.overlay.output.cells import CellValue
from prism.overlay.output.overlay.rush_popup_controller import RushPopupController
from prism.overlay.team_types import TeamDangerBannerData


def make_banner(text: str) -> TeamDangerBannerData:
    return TeamDangerBannerData(
        headline=CellValue.monochrome(text, "snow"),
        team_summary_line=None,
    )


def test_initial_state_returns_none() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    assert controller.timeout_seconds == 10.0
    assert controller.is_active is False
    assert controller.popup_deadline is None
    assert controller.last_handled_who_counter == 0
    assert controller.last_banner is None

    result = controller.tick(
        now=100.0,
        who_counter=0,
        in_lobby_or_game=True,
        banner=None,
    )
    assert result is None
    assert controller.is_active is False


def test_who_counter_increased_banner_none() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    result = controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=None,
    )
    assert result is None
    assert controller.is_active is False
    assert controller.last_handled_who_counter == 0


def test_who_counter_increased_banner_loading() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    loading_banner = make_banner("TEAM DANGER: Loading enemy stats (2 pending)...")
    result = controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=loading_banner,
    )
    assert result is None
    assert controller.is_active is False
    assert controller.last_handled_who_counter == 0


def test_calculation_ready_activates_popup() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    ready_banner = make_banner("OPENING TARGET (STATS): [RED] Danger 55")
    result = controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=ready_banner,
    )
    assert result == ready_banner
    assert controller.is_active is True
    assert controller.last_handled_who_counter == 1
    assert controller.popup_deadline == 110.0
    assert controller.last_banner == ready_banner


def test_ticks_before_deadline_return_banner() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    ready_banner = make_banner("OPENING TARGET (STATS): [RED] Danger 55")
    controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=ready_banner,
    )

    # Subsequent tick with banner=None (no redraw) before deadline
    result_none_banner = controller.tick(
        now=105.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=None,
    )
    assert result_none_banner == ready_banner
    assert controller.is_active is True


def test_updated_banner_during_display_window() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    banner1 = make_banner("OPENING TARGET (STATS): [RED] Danger 55")
    controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=banner1,
    )

    # During display window, an updated banner arrives (e.g. denick or team tag)
    banner2 = make_banner("OPENING TARGET (STATS): [BLUE] Danger 70")
    result = controller.tick(
        now=103.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=banner2,
    )
    assert result == banner2
    assert controller.last_banner == banner2

    # If an unexpected loading banner arrives while active, keep previous banner
    loading_banner = make_banner("TEAM DANGER: Loading enemy stats (1 pending)...")
    result_loading = controller.tick(
        now=104.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=loading_banner,
    )
    assert result_loading == banner2


def test_tick_at_and_after_deadline_returns_none() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    ready_banner = make_banner("OPENING TARGET (STATS): [RED] Danger 55")
    controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=ready_banner,
    )

    # Exactly at deadline
    result_at_deadline = controller.tick(
        now=110.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=ready_banner,
    )
    assert result_at_deadline is None
    assert controller.is_active is False
    assert controller.popup_deadline is None
    assert controller.last_banner is None

    # After deadline
    result_after_deadline = controller.tick(
        now=115.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=ready_banner,
    )
    assert result_after_deadline is None
    assert controller.is_active is False


def test_reset_on_not_in_lobby_or_game() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    ready_banner = make_banner("OPENING TARGET (STATS): [RED] Danger 55")
    controller.tick(
        now=100.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=ready_banner,
    )
    assert controller.is_active is True

    # Not in lobby or game (e.g. left game, or in duels)
    result = controller.tick(
        now=102.0,
        who_counter=1,
        in_lobby_or_game=False,
        banner=ready_banner,
    )
    assert result is None
    assert controller.is_active is False
    assert controller.popup_deadline is None
    assert controller.last_handled_who_counter == 1
    assert controller.last_banner is None


def test_instant_calculation_on_cached_stats() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    cached_banner = make_banner("OPENING TARGET (STATS): [YELLOW] Danger 40")
    # First tick already has who_counter=1 and banner ready
    result = controller.tick(
        now=10.0,
        who_counter=1,
        in_lobby_or_game=True,
        banner=cached_banner,
    )
    assert result == cached_banner
    assert controller.is_active is True
    assert controller.popup_deadline == 20.0


def test_loading_then_resolving() -> None:
    controller = RushPopupController.create(timeout_seconds=10.0)
    loading_banner = make_banner("TEAM DANGER: Loading enemy stats (2 pending)...")

    # Tick 1: loading
    res1 = controller.tick(
        now=50.0, who_counter=1, in_lobby_or_game=True, banner=loading_banner
    )
    assert res1 is None
    assert controller.is_active is False

    # Tick 2: still loading
    res2 = controller.tick(
        now=51.0, who_counter=1, in_lobby_or_game=True, banner=loading_banner
    )
    assert res2 is None
    assert controller.is_active is False

    # Tick 3: resolved!
    ready_banner = make_banner("OPENING TARGET (STATS): [RED] Danger 80")
    res3 = controller.tick(
        now=52.0, who_counter=1, in_lobby_or_game=True, banner=ready_banner
    )
    assert res3 == ready_banner
    assert controller.is_active is True
    assert controller.popup_deadline == 62.0
