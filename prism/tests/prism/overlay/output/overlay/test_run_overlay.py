import unittest.mock
from dataclasses import replace

import pytest

from prism.flashlight.auth.errors import CredentialRejectedError
from prism.overlay.controller import OverlayController
from prism.overlay.events import (
    BedwarsFinalKillEvent,
    ChatMessageEvent,
    EndBedwarsGameEvent,
    Event,
    LobbyListEvent,
    StartBedwarsGameEvent,
    WhisperCommandSetTeamEvent,
)
from prism.overlay.output.cells import InfoCellValue
from prism.overlay.output.overlay.run_overlay import (
    SIGNIN_SUGGESTION_TEXT,
    get_inactive_info_cell,
    get_microsoft_signin_ended_info_cell,
    get_new_data,
    get_signin_suggestion_info_cell,
    get_stat_list,
)
from prism.overlay.output.overlay.stats_overlay import StatsOverlay
from prism.overlay.player_cache import PlayerCache
from prism.overlay.process_event import process_event
from prism.overlay.server import Server
from prism.overlay.visibility import Hidden, Shown
from prism.player import KnownPlayer, PendingPlayer, Player
from tests.prism.auth_utils import (
    make_auth_manager,
    make_microsoft_auth_manager,
    make_session,
)
from tests.prism.overlay.utils import (
    create_controller,
    create_state,
    make_player,
    make_settings,
)

paul = make_player("player", "Paul")
kynes = make_player("player", "Liet", nick="Kynes")
liet = make_player("player", "Liet")
piter = make_player("nick", "Piter")
leto = make_player("pending", "Leto")


def make_player_cache(*players: Player) -> PlayerCache:
    cache = PlayerCache()
    for player in players:
        if isinstance(player, PendingPlayer):
            _, set_pending = cache.get_cached_player_or_set_pending(player.username)
            assert set_pending
            continue

        username = player.username
        if isinstance(player, KnownPlayer) and player.nick is not None:
            username = player.nick

        cache.set_cached_player(username, player, cache.current_genus)
    return cache


FULL_CACHE = make_player_cache(paul, kynes, liet, piter, leto)


def test_get_stat_list_no_redraw() -> None:
    assert get_stat_list(create_controller()) is None


@pytest.mark.parametrize(
    "controller, expected_requested_stats, result",
    (
        # No players in the lobby
        (create_controller(), set(), []),
        (
            # Cache miss -> Request and return pending
            create_controller(state=create_state(lobby_players={"Paul"})),
            {"Paul"},
            [make_player("pending", "Paul")],
        ),
        # Different kinds of players
        (
            create_controller(
                state=create_state(lobby_players={"Paul"}), player_cache=FULL_CACHE
            ),
            set(),
            [paul],
        ),
        (
            create_controller(
                state=create_state(lobby_players={"Kynes"}), player_cache=FULL_CACHE
            ),
            set(),
            [kynes],
        ),
        (
            create_controller(
                state=create_state(lobby_players={"Liet"}), player_cache=FULL_CACHE
            ),
            set(),
            [liet],
        ),
        (
            create_controller(
                state=create_state(lobby_players={"Leto"}), player_cache=FULL_CACHE
            ),
            set(),
            [leto],
        ),
        (
            # Cache miss -> Request and return pending
            create_controller(state=create_state(lobby_players={"Leto"})),
            {"Leto"},
            [leto],
        ),
        (
            # Bunch of players, properly sorted
            create_controller(
                state=create_state(lobby_players={"Paul", "Kynes", "Piter", "Leto"}),
                player_cache=FULL_CACHE,
            ),
            set(),
            [piter, kynes, paul, leto],
        ),
        (
            # Only show alive players
            create_controller(
                settings=make_settings(hide_dead_players=True),
                state=create_state(
                    lobby_players={"Paul", "Kynes", "Piter", "Leto"},
                    alive_players={"Paul", "Kynes"},
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [kynes, paul],
        ),
        (
            # Show all players
            create_controller(
                settings=make_settings(hide_dead_players=False),
                state=create_state(
                    lobby_players={"Paul", "Kynes", "Piter", "Leto"},
                    alive_players={"Paul", "Kynes"},
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [piter, kynes, paul, leto],
        ),
        (
            # Sort correctly wrt party
            create_controller(
                state=create_state(
                    lobby_players={"Paul", "Kynes", "Piter", "Leto"},
                    party_members={"Piter", "Paul"},
                    own_username="Paul",
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [kynes, leto, piter, paul],
        ),
        (
            # Cache miss on all
            create_controller(
                state=create_state(lobby_players={"Paul", "Kynes", "Piter", "Leto"}),
            ),
            {"Paul", "Kynes", "Piter", "Leto"},
            [
                make_player("pending", "Kynes"),
                make_player("pending", "Leto"),
                make_player("pending", "Paul"),
                make_player("pending", "Piter"),
            ],
        ),
        (
            # Duplicate nicked player
            create_controller(
                state=create_state(
                    lobby_players={"Liet", "Kynes"},
                    party_members={"Liet"},
                    own_username="Liet",
                ),
                player_cache=FULL_CACHE,
            ),
            set(),
            [kynes],
        ),
        (
            # Duplicate nicked player, but nicked is pending
            create_controller(
                state=create_state(
                    lobby_players={"Liet", "Kynes"},
                    party_members={"Liet"},
                    own_username="Liet",
                ),
                player_cache=make_player_cache(liet),
            ),
            {"Kynes"},
            # We don't know that Kynes denicks to Liet, so we show both
            [make_player("pending", "Kynes"), liet],
        ),
        (
            # Duplicate nicked player, but un-nicked is pending
            create_controller(
                state=create_state(
                    lobby_players={"Liet", "Kynes"},
                    party_members={"Liet"},
                    own_username="Liet",
                ),
                player_cache=make_player_cache(kynes),
            ),
            {"Liet"},
            # Even though Liet is still pending, we know that the username matches
            # with Kynes, so we can remove Liet
            [kynes],
        ),
    ),
)
def test_get_stat_list(
    controller: OverlayController,
    expected_requested_stats: set[str],
    result: list[Player],
) -> None:
    controller.redraw_event.set()

    assert get_stat_list(controller) == result
    requested_stats = {
        controller.requested_stats_queue.get_nowait()
        for _ in range(controller.requested_stats_queue.qsize())
    }
    assert requested_stats == expected_requested_stats


def test_no_signin_ended_info_cell_while_signed_in() -> None:
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[make_session(tier="microsoft")]
    )
    manager.reconcile()

    assert get_microsoft_signin_ended_info_cell(manager) is None


def test_signin_ended_info_cell_until_dismissed() -> None:
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[make_session()],
    )
    manager.reconcile()

    assert get_microsoft_signin_ended_info_cell(manager) == InfoCellValue(
        text="Microsoft sign-in ended - sign in again in settings",
        color="orange",
        url=None,
    )

    manager.dismiss_signin_ended()

    assert get_microsoft_signin_ended_info_cell(manager) is None


def test_signin_suggestion_info_cell_until_dismissed() -> None:
    manager, _, _ = make_auth_manager(login_results=[make_session()])
    manager.reconcile()
    assert get_signin_suggestion_info_cell(manager) is None

    manager.note_rate_limited()

    assert get_signin_suggestion_info_cell(manager) == InfoCellValue(
        text=SIGNIN_SUGGESTION_TEXT, color="light blue", url=None
    )

    manager.dismiss_signin_suggestion()

    assert get_signin_suggestion_info_cell(manager) is None


@pytest.mark.parametrize(
    "server, only_activate_on_hypixel, text",
    (
        (None, True, None),
        (Server.from_host("mc.hypixel.net"), True, None),
        (Server.from_host("1.2.3.4"), True, None),
        (Server.from_host("bedwarspractice.club"), False, None),
        (
            Server.from_host("bedwarspractice.club"),
            True,
            "Inactive: not on Hypixel (bedwarspractice.club). See settings.",
        ),
        (
            Server.singleplayer(),
            True,
            "Inactive: not on Hypixel (singleplayer). See settings.",
        ),
    ),
)
def test_inactive_info_cell(
    server: Server | None, only_activate_on_hypixel: bool, text: str | None
) -> None:
    controller = create_controller(
        state=create_state(server=server),
        settings=make_settings(only_activate_on_hypixel=only_activate_on_hypixel),
    )
    assert get_inactive_info_cell(controller) == (
        None if text is None else InfoCellValue(text=text, color="light blue", url=None)
    )


def test_get_new_data_no_redraw() -> None:
    auth, _, _ = make_auth_manager()
    controller = create_controller()
    # redraw_event not set -> get_new_data returns (visibility, info_cells, None, None)
    visibility, info_cells, rows, banner = get_new_data(controller, auth)
    assert rows is None
    assert banner is None


def test_team_danger_7_step_sequence_gate() -> None:
    """Mandatory End-to-End Integration Sequence Gate (WP5).

    Covers Steps 1 through 7 of the add-on lifecycle:
    1. /who arrives with pending stats
    2. Stats resolve + denicked ally recognized as friendly
    3. Partial & full team assignments + friendly team confirmation
    4. Final kill + hide_dead_players toggling + midgame transition
    5. Mid-game /who preserving active team assignments
    6. Hidden window caching & Tab-show flush
    7. Unsupported mode (duel suppression) & game end / lobby swap reset
    """
    auth, _, _ = make_auth_manager()

    # Step 1: /who arrives with pending stats
    # ONLINE: Me, AllyNick, RedCarry, RedSupport, BlueCarry, BluePending, GreenUnknown
    me_player = make_player("player", "Me", stars=50.0, fkdr=2.0)
    ally_nick = make_player("nick", "AllyNick")
    red_carry = make_player(
        "player",
        "RedCarry",
        stars=400.0,
        fkdr=8.0,
        bblr=3.0,
        wlr=3.0,
        winstreak=10,
        winstreak_accurate=True,
    )
    red_support = make_player(
        "player",
        "RedSupport",
        stars=50.0,
        fkdr=1.0,
        bblr=0.5,
        wlr=0.5,
    )
    blue_carry = make_player(
        "player",
        "BlueCarry",
        stars=250.0,
        fkdr=5.0,
        bblr=2.0,
        wlr=2.0,
        winstreak=5,
        winstreak_accurate=True,
    )
    blue_pending = make_player("pending", "BluePending")
    green_unknown = make_player("unknown", "GreenUnknown")

    cache = make_player_cache(
        me_player,
        ally_nick,
        red_carry,
        red_support,
        blue_carry,
        blue_pending,
        green_unknown,
    )

    controller = create_controller(
        state=create_state(
            own_username="Me",
            party_members={"Me", "RealAlly"},
            in_queue=True,
        ),
        player_cache=cache,
    )

    # Process /who
    who_event = LobbyListEvent(
        [
            "Me",
            "AllyNick",
            "RedCarry",
            "RedSupport",
            "BlueCarry",
            "BluePending",
            "GreenUnknown",
        ]
    )
    controller.state, _ = process_event(controller, who_event)
    controller.redraw_event.set()

    visibility, info_cells, new_rows, banner = get_new_data(controller, auth)
    assert new_rows is not None
    assert banner is not None
    assert banner.headline.text == "TEAM DANGER: Loading enemy stats (1 pending)..."

    # Step 2: Stats resolve + Denick
    # BluePending resolves to KnownPlayer, AllyNick denicked to RealAlly
    blue_pending_resolved = make_player(
        "player",
        "BluePending",
        stars=120.0,
        fkdr=3.0,
        bblr=1.5,
        wlr=1.5,
    )
    ally_resolved = make_player(
        "player",
        "RealAlly",
        nick="AllyNick",
        stars=200.0,
        fkdr=4.0,
        bblr=2.0,
        wlr=2.0,
    )
    cache.set_cached_player("BluePending", blue_pending_resolved, cache.current_genus)
    cache.set_cached_player("AllyNick", ally_resolved, cache.current_genus)
    controller.redraw_event.set()

    visibility, info_cells, new_rows, banner = get_new_data(controller, auth)
    assert new_rows is not None
    assert banner is not None
    assert banner.headline.text.startswith("TOP UNASSIGNED THREAT: RedCarry")
    assert banner.team_summary_line is None

    # Step 3: Partial -> Full team assignments + friendly team confirmation
    # [SHOUT] [RED] RedCarry
    # /w !r=RedSupport
    # /w !b=BlueCarry,BluePending
    # /w !g=GreenUnknown
    # [YELLOW] AllyNick
    events: list[Event] = [
        ChatMessageEvent(username="RedCarry", message="hi", team="red"),
        WhisperCommandSetTeamEvent(team="red", usernames=["RedSupport"]),
        WhisperCommandSetTeamEvent(team="blue", usernames=["BlueCarry", "BluePending"]),
        WhisperCommandSetTeamEvent(team="green", usernames=["GreenUnknown"]),
        ChatMessageEvent(username="AllyNick", message="inc", team="yellow"),
    ]
    for ev in events:
        controller.state, _ = process_event(controller, ev)

    controller.redraw_event.set()
    visibility, info_cells, new_rows, banner = get_new_data(controller, auth)
    assert new_rows is not None
    assert banner is not None
    # Opening phase priority target is red (carry + support > blue)
    assert banner.headline.text.startswith("OPENING TARGET (STATS): [RED]")
    # Yellow is friendly, excluded from enemy summary line; green unknown is included
    assert banner.team_summary_line is not None
    assert "[RED]" in banner.team_summary_line.text
    assert "[BLUE]" in banner.team_summary_line.text
    assert "[GREEN]" in banner.team_summary_line.text
    assert "[YELLOW]" not in banner.team_summary_line.text

    # Rows have [R], [B], [G], [Y] prefixes
    row_usernames = [r[1].username.text for r in new_rows]
    assert any(u.startswith("[R] ") for u in row_usernames)
    assert any(u.startswith("[B] ") for u in row_usernames)
    assert any(u.startswith("[G] ") for u in row_usernames)
    assert any(u.startswith("[Y] ") for u in row_usernames)

    # Step 4: Final kill + hide_dead_players toggling + phase transition
    # Game starts and enters midgame (time > 90s)
    game_start = StartBedwarsGameEvent(is_bedwars_duel=False)
    controller.state, _ = process_event(controller, game_start)
    controller.state = replace(
        controller.state, last_game_start=0.0, now_func=lambda: 100.0
    )

    kill_event = BedwarsFinalKillEvent(
        dead_player="RedCarry", raw_message="RedCarry died"
    )
    controller.state, _ = process_event(controller, kill_event)
    assert controller.state.has_final_kills_or_deaths

    # Subtest 4a: hide_dead_players = True
    controller.settings.hide_dead_players = True
    controller.redraw_event.set()
    visibility, info_cells, new_rows_hidden, banner_hidden = get_new_data(
        controller, auth
    )
    assert new_rows_hidden is not None
    assert banner_hidden is not None
    # RedCarry is omitted from rows
    assert not any("RedCarry" in r[1].username.text for r in new_rows_hidden)
    # Phase transitions to midgame: TOP ALIVE THREAT: [BLUE]
    assert banner_hidden.headline.text.startswith("TOP ALIVE THREAT: [BLUE]")

    # Subtest 4b: hide_dead_players = False
    controller.settings.hide_dead_players = False
    controller.redraw_event.set()
    visibility, info_cells, new_rows_shown, banner_shown = get_new_data(
        controller, auth
    )
    assert new_rows_shown is not None
    assert banner_shown is not None
    # RedCarry IS in rows
    assert any("RedCarry" in r[1].username.text for r in new_rows_shown)
    # Banner identically excludes RedCarry and still recommends Blue
    assert banner_shown.headline.text.startswith("TOP ALIVE THREAT: [BLUE]")
    # Red has 1 alive in team summary line
    assert banner_shown.team_summary_line is not None
    assert "[RED]" in banner_shown.team_summary_line.text
    assert "(1)" in banner_shown.team_summary_line.text

    # Step 5: Mid-game /who
    # ONLINE: Me, AllyNick, RedSupport, BlueCarry, BluePending
    midgame_who = LobbyListEvent(
        ["Me", "AllyNick", "RedSupport", "BlueCarry", "BluePending"]
    )
    controller.state, _ = process_event(controller, midgame_who)
    # Preserves active teams for alive players
    assert controller.state.team_map["RedSupport"] == "red"
    assert controller.state.team_map["BlueCarry"] == "blue"
    assert controller.state.team_map["BluePending"] == "blue"
    controller.redraw_event.set()
    _, _, _, midgame_banner = get_new_data(controller, auth)
    assert midgame_banner is not None
    assert midgame_banner.headline.text.startswith("TOP ALIVE THREAT: [BLUE]")

    # Step 6: Hidden window caching & Tab show
    mock_main_content = unittest.mock.MagicMock()
    mock_window = unittest.mock.MagicMock()
    mock_window.shown = False

    overlay = StatsOverlay.__new__(StatsOverlay)
    overlay.controller = controller
    overlay.poll_interval = 100
    overlay.visibility = Hidden()
    overlay.last_new_rows = None
    overlay.last_new_banner = None
    overlay.current_page = "main"
    overlay.tab_pressed = False
    overlay.window = mock_window
    overlay.main_content = mock_main_content
    overlay.rush_popup = unittest.mock.MagicMock()
    overlay.rush_popup_controller = unittest.mock.MagicMock()
    overlay.rush_popup_controller.tick.return_value = None

    # While hidden, updates occur
    controller.redraw_event.set()
    cached_vis, cached_info, cached_rows, cached_banner = get_new_data(controller, auth)
    overlay.get_new_data = lambda: (
        Hidden(),
        cached_info,
        cached_rows,
        cached_banner,
    )
    overlay.update_overlay()
    mock_main_content.update_content.assert_not_called()
    assert overlay.last_new_rows == cached_rows
    assert overlay.last_new_banner == cached_banner

    # Tab pressed -> window shown, flush occurs
    mock_window.shown = True
    overlay.tab_pressed = True
    overlay.get_new_data = lambda: (Shown(), [], None, None)
    overlay.update_overlay()
    mock_main_content.update_content.assert_called_once_with(
        [], cached_rows, cached_banner
    )
    assert overlay.last_new_rows is None
    assert overlay.last_new_banner is None

    # Step 7: Unsupported mode & New match reset
    # 7a: Bedwars duel started -> banner is suppressed (None)
    duel_start = StartBedwarsGameEvent(is_bedwars_duel=True)
    controller.state, _ = process_event(controller, duel_start)
    controller.redraw_event.set()
    _, _, _, duel_banner = get_new_data(controller, auth)
    assert duel_banner is None

    # 7b: Match end -> player_teams cleared, banner resets to None
    end_event = EndBedwarsGameEvent()
    controller.state, _ = process_event(controller, end_event)
    assert controller.state.player_teams == frozenset()
    controller.redraw_event.set()
    _, _, _, end_banner = get_new_data(controller, auth)
    assert end_banner is None
