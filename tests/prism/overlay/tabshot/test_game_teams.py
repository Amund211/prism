from prism.overlay.tabshot.game_teams import TEAM_COLOR_SECONDS, GameTeams


def test_game_teams() -> None:
    teams = GameTeams()
    assert teams.for_game(None, now=0.0) == {}
    assert teams.for_game(1.0, now=0.0) == {}

    teams = teams.replace(1.0, {"a": "red", "b": "blue"}, now=10.0)
    assert teams.for_game(1.0, now=10.0) == {"a": "red", "b": "blue"}
    assert teams.for_game(2.0, now=10.0) == {}
    assert teams.for_game(None, now=10.0) == {}

    # Each Tab press replaces the old result, so a bad read is easy to see
    teams = teams.replace(1.0, {"c": "aqua"}, now=11.0)
    assert teams.for_game(1.0, now=11.0) == {"c": "aqua"}

    teams = teams.replace(1.0, {}, now=12.0)
    assert teams.for_game(1.0, now=12.0) == {}

    # Outside a game
    teams = teams.replace(None, {"e": "white"}, now=13.0)
    assert teams.for_game(None, now=13.0) == {"e": "white"}


def test_game_teams_expire() -> None:
    teams = GameTeams().replace(1.0, {"a": "red"}, now=10.0)
    assert teams.for_game(1.0, now=10.0 + TEAM_COLOR_SECONDS - 0.1) == {"a": "red"}
    assert teams.for_game(1.0, now=10.0 + TEAM_COLOR_SECONDS) == {}
