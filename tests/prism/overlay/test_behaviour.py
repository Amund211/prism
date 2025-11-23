import io
import queue
import unittest.mock
from dataclasses import dataclass, replace
from typing import cast

import pytest

from prism import VERSION_STRING
from prism.errors import APIError, PlayerNotFoundError
from prism.overlay.behaviour import (
    autodenick_teammate,
    bedwars_game_ended,
    get_and_cache_player,
    set_nickname,
    should_redraw,
    update_settings,
)
from prism.overlay.controller import OverlayController
from prism.overlay.keybinds import AlphanumericKeyDict
from prism.overlay.nick_database import NickDatabase
from prism.overlay.settings import NickValue, Settings, SettingsDict, get_settings
from prism.player import MISSING_WINSTREAKS, Account, KnownPlayer, Tags, Winstreaks
from tests.prism.overlay import test_get_stats
from tests.prism.overlay.test_settings import (
    DEFAULT_STATS_THREAD_COUNT,
    noop_update_settings,
)
from tests.prism.overlay.utils import (
    CUSTOM_RATING_CONFIG_COLLECTION_DICT,
    MockedAccountProvider,
    MockedPlayerProvider,
    MockedTagsProvider,
    MockedWinstreakProvider,
    create_controller,
    create_state,
    make_player,
    make_settings,
    make_winstreaks,
    no_close,
)

USERNAME = "MyIGN"
NICK = "AmazingNick"
UUID = "MyUUID"


def set_known_nicks(known_nicks: dict[str, str], controller: OverlayController) -> None:
    """Update the settings and nickdatabase with the uuid->nick mapping"""
    for uuid, nick in known_nicks.items():
        controller.settings.known_nicks[nick] = {"uuid": uuid, "comment": ""}
        controller.nick_database.default_database[nick] = uuid


KNOWN_NICKS: tuple[dict[str, str], ...] = (
    {},  # No previous known nick
    {"someotheruuid": "randomnick"},  # No prev. known + known for other player
    {UUID: "randomnick"},  # Known different
    {UUID: NICK},  # Known same as new (when setting)
    {UUID: "randomnick", "someotheruuid": "randomnick2"},
)


@pytest.mark.parametrize("known_nicks", KNOWN_NICKS)
def test_set_nickname(known_nicks: dict[str, str]) -> None:
    """Assert that set_nickname works when setting a nick"""
    settings_file = no_close(io.StringIO())

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=lambda username: Account(
                username=username, uuid=UUID
            )
        ),
        settings=make_settings(write_settings_file_utf8=lambda: settings_file),
    )
    controller.player_cache.uncache_player = unittest.mock.MagicMock()  # type: ignore

    set_known_nicks(known_nicks, controller)

    set_nickname(nick=NICK, username=USERNAME, controller=controller)

    # Known nicks updated
    for uuid, nick in known_nicks.items():
        if uuid == UUID and nick != NICK:
            # The player's nick is updated so the old entry should be gone
            assert controller.settings.known_nicks.get(nick, None) is None
            assert controller.nick_database.get(nick) is None
        else:
            # Other players should not be affected
            assert controller.settings.known_nicks[nick] == {
                "uuid": uuid,
                "comment": "",
            }
            assert controller.nick_database.default_database[nick] == uuid

    # Nick updated in settings
    assert controller.settings.known_nicks.get(NICK, None) == {
        "uuid": UUID,
        # Comment is kept if the nick is updated
        "comment": USERNAME if UUID not in known_nicks else "",
    }

    # Settings stored
    stored_settings = get_settings(
        read_settings_file_utf8=lambda: io.StringIO(settings_file.getvalue()),
        write_settings_file_utf8=lambda: io.StringIO(),
        default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
        update_settings=noop_update_settings,
    )
    assert stored_settings == controller.settings

    # Nick updated in database
    assert controller.nick_database.get(NICK) == UUID

    # Cache dropped for new nick
    expected_calls = [unittest.mock.call(NICK)]

    # Cache dropped for old nick
    if UUID in known_nicks and NICK != known_nicks[UUID]:
        expected_calls.append(unittest.mock.call(known_nicks[UUID]))

    assert sorted(controller.player_cache.uncache_player.mock_calls) == sorted(
        expected_calls
    )

    # Redraw event set
    assert controller.redraw_event.is_set()


@pytest.mark.parametrize("explicit", (False, True))
@pytest.mark.parametrize("known_nicks", KNOWN_NICKS)
def test_unset_nickname(known_nicks: dict[str, str], explicit: bool) -> None:
    """
    Assert that set_nickname works when unsetting a nick

    Unsetting is either explicit with username=None, or when the uuid of the player
    can't be found
    """
    settings_file = no_close(io.StringIO())

    def get_account_by_username(_: str) -> Account:
        if explicit:
            return Account(username=USERNAME, uuid=UUID)

        raise PlayerNotFoundError

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
        settings=make_settings(write_settings_file_utf8=lambda: settings_file),
    )
    controller.player_cache.uncache_player = unittest.mock.MagicMock()  # type: ignore

    set_known_nicks(known_nicks, controller)

    set_nickname(
        nick=NICK, username=None if explicit else USERNAME, controller=controller
    )

    # Nick updated in settings
    assert controller.settings.known_nicks.get(NICK, None) is None

    # Settings stored
    stored_settings = get_settings(
        read_settings_file_utf8=lambda: io.StringIO(settings_file.getvalue()),
        write_settings_file_utf8=lambda: io.StringIO(),
        default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
        update_settings=noop_update_settings,
    )
    assert stored_settings == controller.settings

    # Nick updated in database
    assert controller.nick_database.get(NICK) is None

    # Cache dropped for reset nick
    controller.player_cache.uncache_player.assert_called_once_with(NICK)

    # Redraw event set
    assert controller.redraw_event.is_set()


@pytest.mark.parametrize(
    "redraw_event_set, completed_stats, result",
    (
        (False, (), False),
        (False, ("Random1", "Random2"), False),
        (True, (), True),
        (False, ("Random1", "Random2", "OwnUsername"), True),
        (True, ("Player1", "Random2", "OwnUsername"), True),
    ),
)
def test_should_redraw(
    redraw_event_set: bool, completed_stats: tuple[str], result: bool
) -> None:
    controller = create_controller(
        state=create_state(
            lobby_players={"OwnUsername", "Player1", "Player2"}, in_queue=True
        )
    )

    if redraw_event_set:
        controller.redraw_event.set()

    for username in completed_stats:
        controller.completed_stats_queue.put_nowait(username)

    assert should_redraw(controller) == result


@pytest.mark.parametrize("player_has_winstreaks", (True, False))
@pytest.mark.parametrize("estimated_winstreaks_from_provider", (True, False))
def test_get_and_cache_stats(
    player_has_winstreaks: bool, estimated_winstreaks_from_provider: bool
) -> None:
    base_user = test_get_stats.users["NickedPlayer"]

    # For typing
    assert base_user.player is not None

    player_without_winstreaks = replace(
        base_user.player,
        stats=replace(base_user.player.stats, wins=40),
    )
    player_with_winstreaks = replace(
        base_user.player,
        stats=replace(base_user.player.stats, wins=40),
    ).update_winstreaks(
        overall=10,
        solo=10,
        doubles=10,
        threes=10,
        fours=10,
        winstreaks_accurate=True,
    )

    user = (
        replace(base_user, player=player_with_winstreaks)
        if player_has_winstreaks
        else replace(base_user, player=player_without_winstreaks)
    )
    assert user.nick is not None  # For typing

    def get_estimated_winstreaks(uuid: str) -> tuple[Winstreaks, bool]:
        assert uuid == user.uuid

        if estimated_winstreaks_from_provider:
            return (
                make_winstreaks(
                    overall=100, solo=100, doubles=100, threes=100, fours=100
                ),
                True,
            )

        return (MISSING_WINSTREAKS, False)

    def get_account_by_username(username: str) -> Account:
        if username == user.nick:
            raise PlayerNotFoundError

        assert username == user.username
        return Account(username=user.username, uuid=user.uuid)

    def get_player(uuid: str, user_id: str) -> KnownPlayer:
        assert uuid == user.uuid
        assert user.player is not None

        return user.player

    def get_tags(uuid: str, user_id: str, urchin_api_key: str | None) -> Tags:
        assert uuid == user.uuid
        assert urchin_api_key is None

        return Tags(
            cheating="none",
            sniping="none",
        )

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
        player_provider=MockedPlayerProvider(get_player=get_player),
        winstreak_provider=MockedWinstreakProvider(
            get_estimated_winstreaks_for_uuid=get_estimated_winstreaks
        ),
        tags_provider=MockedTagsProvider(get_tags=get_tags),
        nick_database=NickDatabase([{user.nick: user.uuid}]),
    )

    completed_queue = queue.Queue[str]()

    get_and_cache_player(user.nick, completed_queue, controller)

    # One update for getting the stats
    assert completed_queue.get_nowait() == user.nick

    # One update for getting the tags
    assert completed_queue.get_nowait() == user.nick

    # One update for getting estimated winstreaks - only when missing + gotten
    if not player_has_winstreaks and estimated_winstreaks_from_provider:
        assert completed_queue.get_nowait() == user.nick
    else:
        with pytest.raises(queue.Empty):
            completed_queue.get_nowait()


def test_get_and_cache_stats_tags_error() -> None:
    user = test_get_stats.users["NickedPlayer"]
    assert user.nick is not None  # For typing

    def get_estimated_winstreaks(uuid: str) -> tuple[Winstreaks, bool]:
        assert uuid == user.uuid
        return (MISSING_WINSTREAKS, False)

    def get_account_by_username(username: str) -> Account:
        if username == user.nick:
            raise PlayerNotFoundError

        assert username == user.username
        return Account(username=user.username, uuid=user.uuid)

    def get_player(uuid: str, user_id: str) -> KnownPlayer:
        assert uuid == user.uuid
        assert user.player is not None

        return user.player

    def get_tags(uuid: str, user_id: str, urchin_api_key: str | None) -> Tags:
        assert uuid == user.uuid
        assert urchin_api_key is None

        raise APIError("API failure")

    controller = create_controller(
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
        player_provider=MockedPlayerProvider(get_player=get_player),
        winstreak_provider=MockedWinstreakProvider(
            get_estimated_winstreaks_for_uuid=get_estimated_winstreaks
        ),
        tags_provider=MockedTagsProvider(get_tags=get_tags),
        nick_database=NickDatabase([{user.nick: user.uuid}]),
    )

    completed_queue = queue.Queue[str]()

    get_and_cache_player(user.nick, completed_queue, controller)

    # One update for getting the stats
    assert completed_queue.get_nowait() == user.nick

    # No update for winstreak
    # No update since we failed getting tags
    with pytest.raises(queue.Empty):
        completed_queue.get_nowait()


def test_update_settings_nothing() -> None:
    settings_file = no_close(io.StringIO())
    controller = create_controller(
        settings=make_settings(write_settings_file_utf8=lambda: settings_file),
    )
    settings_before = replace(controller.settings)

    # Make sure player cache and nick database aren't updated
    controller.player_cache = None  # type: ignore
    controller.nick_database.databases.clear()

    update_settings(settings_before.to_dict(), controller)

    # We store the settings every time, even if no changes occurred.
    stored_settings = get_settings(
        read_settings_file_utf8=lambda: io.StringIO(settings_file.getvalue()),
        write_settings_file_utf8=lambda: io.StringIO(),
        default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
        update_settings=noop_update_settings,
    )
    assert controller.settings == stored_settings == settings_before


def test_update_settings_known_nicks() -> None:
    settings_file = no_close(io.StringIO())

    controller = create_controller(
        settings=make_settings(
            known_nicks={
                "SuperbNick": {"uuid": "2", "comment": "2"},
                "OldNick": {"uuid": "5", "comment": "5"},
            },
            write_settings_file_utf8=lambda: settings_file,
        ),
    )

    known_nicks: dict[str, NickValue] = {
        "AmazingNick": {"uuid": "1", "comment": "1"},
        "SuperbNick": {"uuid": "42", "comment": "42"},
    }

    new_settings = make_settings(known_nicks=known_nicks).to_dict()

    controller.player_cache.clear_cache = unittest.mock.MagicMock()  # type: ignore
    controller.player_cache.uncache_player = unittest.mock.MagicMock()  # type: ignore

    update_settings(new_settings, controller)

    stored_settings = get_settings(
        read_settings_file_utf8=lambda: io.StringIO(settings_file.getvalue()),
        write_settings_file_utf8=lambda: io.StringIO(),
        default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
        update_settings=noop_update_settings,
    )
    assert controller.settings == stored_settings
    assert controller.settings.known_nicks == known_nicks

    assert controller.nick_database.default_database == {
        "AmazingNick": "1",
        "SuperbNick": "42",
    }

    controller.player_cache.clear_cache.assert_not_called()
    controller.player_cache.uncache_player.assert_has_calls(
        tuple(map(unittest.mock.call, ("AmazingNick", "SuperbNick", "OldNick"))),
        any_order=True,
    )
    assert controller.player_cache.uncache_player.call_count == 3

    # Nicknames changed, so we want to redraw
    assert controller.redraw_event.is_set()


def test_update_settings_everything_changed() -> None:
    settings_file = no_close(io.StringIO())
    settings = make_settings(
        known_nicks={
            "AmazingNick": {"uuid": "1", "comment": "1"},
            "SuperbNick": {"uuid": "2", "comment": "2"},
            "AstoundingNick": {"uuid": "3", "comment": "3"},
        },
        write_settings_file_utf8=lambda: settings_file,
    )

    controller = create_controller(
        settings=settings,
    )

    # NOTE: Make sure everything specified here is different from its default value
    new_settings = SettingsDict(
        user_id="my-user-id",
        hypixel_api_key="my-new-hypixel-api-key",
        urchin_api_key="01234567-89ab-cdef-0123-456789abcdef",
        sort_order="wlr",
        column_order=("username", "winstreak"),
        rating_configs=CUSTOM_RATING_CONFIG_COLLECTION_DICT,
        known_nicks={
            "AmazingNick": {"uuid": "1", "comment": "my friend :)"},
            "SuperbNick": {"uuid": "42", "comment": "42"},
        },
        autodenick_teammates=False,
        autoselect_logfile=False,
        autohide_timeout=6,
        show_on_tab=False,
        show_on_tab_keybind=AlphanumericKeyDict(
            name="a", char="a", key_type="alphanumeric"
        ),
        autowho=False,
        autowho_delay=4.5,
        chat_hotkey=AlphanumericKeyDict(name="u", char="u", key_type="alphanumeric"),
        activate_in_bedwars_duels=True,
        check_for_updates=False,
        include_patch_updates=True,
        use_included_certs=False,
        stats_thread_count=12,
        discord_rich_presence=False,
        discord_show_username=False,
        discord_show_session_stats=False,
        discord_show_party=True,
        hide_dead_players=False,
        disable_overrideredirect=True,
        hide_with_alpha=True,
        alpha_hundredths=20,
        # NOTE: Don't expect to update version info through update_settings
        #       but testing this here regardless
        last_version=VERSION_STRING,
        greatest_version="v123.1.0",
    )

    controller.player_cache.clear_cache = unittest.mock.MagicMock()  # type: ignore
    controller.player_cache.uncache_player = unittest.mock.MagicMock()  # type: ignore

    update_settings(new_settings, controller)

    stored_settings = get_settings(
        read_settings_file_utf8=lambda: io.StringIO(settings_file.getvalue()),
        write_settings_file_utf8=lambda: io.StringIO(),
        default_stats_thread_count=DEFAULT_STATS_THREAD_COUNT,
        update_settings=noop_update_settings,
    )

    # We store the settings every time, even if no changes occurred.
    assert (
        controller.settings
        == stored_settings
        == Settings.from_dict(
            new_settings, write_settings_file_utf8=lambda: io.StringIO()
        )
    )

    assert controller.nick_database.default_database == {
        "AmazingNick": "1",
        "SuperbNick": "42",
    }

    # Nicknames changed, so individual players should be uncached
    # (not whole cache cleared)
    controller.player_cache.clear_cache.assert_not_called()
    # AmazingNick updated (comment changed),
    # SuperbNick updated (uuid changed), and AstoundingNick removed
    assert controller.player_cache.uncache_player.call_count == 3

    # Discord rpc settings changed so we want to update it
    assert controller.update_presence_event.is_set()

    # Lots of stuff changed, so we want to redraw
    assert controller.redraw_event.is_set()


def test_update_settings_clear_urchin_key() -> None:
    controller = create_controller(
        settings=make_settings(urchin_api_key="01234567-89ab-cdef-0123-456789abcdef"),
        urchin_api_key_invalid=True,
    )

    new_settings = replace(controller.settings, urchin_api_key=None)

    update_settings(new_settings.to_dict(), controller)

    assert not controller.urchin_api_key_invalid


def test_update_settings_set_urchin_key() -> None:
    controller = create_controller(
        settings=make_settings(urchin_api_key=None),
        urchin_api_key_invalid=True,
    )

    new_settings = replace(
        controller.settings, urchin_api_key="01234567-89ab-cdef-0123-456789abcdef"
    )

    update_settings(new_settings.to_dict(), controller)

    assert not controller.urchin_api_key_invalid


@dataclass(frozen=True, slots=True)
class LobbyPlayer:
    username: str | None = None
    nick: str | None = None
    manually_denicked: bool = True  # Denicked from settings
    pending: bool = False
    missing: bool = False


autodenick_test_cases: tuple[
    tuple[tuple[LobbyPlayer, ...], set[str], LobbyPlayer | None], ...
] = (
    ((), {"OwnUsername"}, None),
    ((LobbyPlayer(username="OwnUsername"),), {"OwnUsername"}, None),
    ((LobbyPlayer(nick="SomeNick"),), {"OwnUsername"}, None),  # Too few players
    (
        # No nicks
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # One nick, but we are not nicked
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(nick="Nick8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # One nick - us
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        LobbyPlayer(username="OwnUsername", nick="Nick1"),
    ),
    (
        # Two nicks
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(nick="Nick2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # Two missing teammates
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(nick="Nick2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername", "Teammate"},
        None,
    ),
    (
        # Two missing teammates - one nick
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername", "Teammate"},
        None,
    ),
    (
        # Lobby not full
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # Pending stats
        (
            LobbyPlayer(username="Someone", pending=True),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # Missing stats
        (
            LobbyPlayer(username="Someone", missing=True),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # One nick, but already denicked by settings
        (
            LobbyPlayer(username="Someone", nick="SomeNick"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # One nick, but already denicked by api
        (
            LobbyPlayer(username="Someone", nick="SomeNick", manually_denicked=False),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        LobbyPlayer(username="OwnUsername", nick="SomeNick"),
    ),
    (
        # Multiple nicks denicked, one unknown
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(username="Player2", nick="P2Nick"),
            LobbyPlayer(username="Player3", nick="P3Nick"),
            LobbyPlayer(username="Player4", nick="P4Nick"),
            LobbyPlayer(username="Player5", nick="P5Nick"),
            LobbyPlayer(username="Player6", nick="P6Nick"),
            LobbyPlayer(username="Player7", nick="P7Nick"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        LobbyPlayer(username="OwnUsername", nick="Nick1"),
    ),
    (
        # Multiple nicks denicked, one by api. one unknown
        (
            LobbyPlayer(nick="Nick1"),
            LobbyPlayer(
                username="Player2", nick="SomeNickname", manually_denicked=False
            ),
            LobbyPlayer(username="Player3", nick="P3Nick"),
            LobbyPlayer(username="Player4", nick="P4Nick"),
            LobbyPlayer(username="Player5", nick="P5Nick"),
            LobbyPlayer(username="Player6", nick="P6Nick"),
            LobbyPlayer(username="Player7", nick="P7Nick"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # OwnUsername not joined yet somehow
        (
            LobbyPlayer(username="Someone"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
        ),
        {"OwnUsername"},
        None,
    ),
    (
        # One nick - our teammate
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(username="Player9"),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(nick="Nick15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        LobbyPlayer(username="Player15", nick="Nick15"),
    ),
    (
        # Lobby not full
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(username="Player9"),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(nick="Nick15"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        None,
    ),
    (
        # Multiple unknown nicks
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(username="Player9"),
            LobbyPlayer(nick="Nick10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(nick="Nick15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        None,
    ),
    (
        # Multiple unknown nicks + missing teammates
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(nick="Nick9"),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(nick="Nick15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        None,
    ),
    (
        # Api failure causes teammate to be marked as unknown nick
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(nick="Player9"),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(username="Player15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        None,
    ),
    (
        # One nicked player and our teammate denicked by settings
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(username="Player9", nick="AmazingNick"),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(nick="SuperbNick"),
            LobbyPlayer(username="Player15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        None,  # We have all our teammates in the lobby
    ),
    (
        # Our teammate incorrectly denicked by API
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(
                username="SomeoneRandom",
                nick="AmazingNick",
                manually_denicked=False,
            ),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(username="Player15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        LobbyPlayer(username="Player9", nick="AmazingNick"),
    ),
    (
        # Our teammate correctly denicked by API
        (
            LobbyPlayer(username="OwnUsername"),
            LobbyPlayer(username="Player2"),
            LobbyPlayer(username="Player3"),
            LobbyPlayer(username="Player4"),
            LobbyPlayer(username="Player5"),
            LobbyPlayer(username="Player6"),
            LobbyPlayer(username="Player7"),
            LobbyPlayer(username="Player8"),
            LobbyPlayer(
                username="Player9", nick="AmazingNick", manually_denicked=False
            ),
            LobbyPlayer(username="Player10"),
            LobbyPlayer(username="Player11"),
            LobbyPlayer(username="Player12"),
            LobbyPlayer(username="Player13"),
            LobbyPlayer(username="Player14"),
            LobbyPlayer(username="Player15"),
            LobbyPlayer(username="Player16"),
        ),
        {"OwnUsername", "Player3", "Player9", "Player15"},
        # NOTE: We have all our teammates denicked, but we would like to store the
        #       nick of Player9 in settings.
        LobbyPlayer(username="Player9", nick="AmazingNick"),
    ),
)


@pytest.mark.parametrize("lobby, party_members, denick", autodenick_test_cases)
def test_autodenick_teammate(
    lobby: tuple[LobbyPlayer, ...],
    party_members: set[str],
    denick: LobbyPlayer | None,
) -> None:
    assert all(
        (player.username is not None or player.nick is not None)
        and not (player.pending and player.missing)
        and (
            (not player.pending and not player.missing)
            or (player.username is not None and player.nick is None)
        )
        for player in lobby
    )

    if denick is not None:
        assert denick.username is not None
        assert denick.nick is not None
        assert not denick.pending
        assert not denick.missing
        assert denick.manually_denicked

    lobby_players = cast(set[str], {player.nick or player.username for player in lobby})
    assert all(isinstance(player, str) for player in lobby_players)

    def get_account_by_username(username: str) -> Account:
        return Account(username=username, uuid=f"uuid-for-{username}")

    controller = create_controller(
        state=create_state(
            lobby_players=lobby_players,
            party_members=party_members,
            in_queue=True,
            out_of_sync=False,
        ),
        account_provider=MockedAccountProvider(
            get_account_by_username=get_account_by_username
        ),
    )

    # Update the controller state by setting cache and denicks
    for player in lobby:
        if player.pending:
            assert player.username is not None
            controller.player_cache.set_player_pending(player.username)
        elif player.missing:
            # Stats missing completely
            pass
        elif player.username is None:
            assert player.nick is not None
            controller.player_cache.set_cached_player(
                player.nick, make_player(variant="nick", username=player.nick), genus=0
            )
        else:
            if player.nick is not None and player.manually_denicked:
                # Add an entry to the settings/denick database
                set_nickname(
                    username=player.username, nick=player.nick, controller=controller
                )

            controller.player_cache.set_cached_player(
                player.nick or player.username,
                make_player(
                    variant="player",
                    username=player.username,
                    nick=player.nick,
                    uuid=get_account_by_username(player.username).uuid,
                ),
                genus=0,
            )

    with unittest.mock.patch(
        "prism.overlay.behaviour.set_nickname"
    ) as patched_set_nickname:
        autodenick_teammate(controller)

    if denick is None:
        patched_set_nickname.assert_not_called()
    else:
        patched_set_nickname.assert_called_once_with(
            nick=denick.nick, username=denick.username, controller=controller
        )


@pytest.mark.parametrize(
    "controller",
    (
        create_controller(state=create_state(in_queue=False)),
        create_controller(state=create_state(out_of_sync=True)),
        create_controller(
            state=create_state(in_queue=False, out_of_sync=True),
        ),
    ),
)
def test_autodenick_teammate_early_exit(controller: OverlayController) -> None:
    with unittest.mock.patch(
        "prism.overlay.behaviour.set_nickname"
    ) as patched_set_nickname:
        autodenick_teammate(controller)

    patched_set_nickname.assert_not_called()


def test_autodenick_alive_players_mismatch() -> None:
    controller = create_controller(
        state=create_state(
            lobby_players={
                "SomeNick",
                "Player2",
                "Player3",
                "Player4",
                "Player5",
                "Player6",
                "Player7",
                "Player8",
            },
            alive_players={
                "SomeNick",
                "Player2",
                "Player3",
                "Player4",
                "Player5",
                "Player6",
                "Player7",
            },
            in_queue=True,
            out_of_sync=False,
        )
    )

    with unittest.mock.patch(
        "prism.overlay.behaviour.set_nickname"
    ) as patched_set_nickname:
        autodenick_teammate(controller)

    patched_set_nickname.assert_not_called()


def test_bedwars_game_ended() -> None:
    controller = create_controller()
    controller.player_cache.clear_cache = unittest.mock.MagicMock()  # type: ignore

    bedwars_game_ended(controller)

    # Player cache cleared
    controller.player_cache.clear_cache.assert_called_once_with(short_term_only=True)

    # Update presence event set
    assert controller.update_presence_event.is_set()

    # Redraw event NOT set
    assert not controller.redraw_event.is_set()
