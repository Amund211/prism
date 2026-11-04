from prism.overlay.tabshot.game_teams import GameTeams


def test_game_teams() -> None:
    teams = GameTeams()
    assert teams.for_game(None) == {}
    assert teams.for_game(1.0) == {}

    teams = teams.merge(1.0, {"a": "red", "b": "blue"})
    assert teams.for_game(1.0) == {"a": "red", "b": "blue"}
    assert teams.for_game(2.0) == {}
    assert teams.for_game(None) == {}

    # Same game: merge, newest wins
    teams = teams.merge(1.0, {"b": "green", "c": "aqua"})
    assert teams.for_game(1.0) == {"a": "red", "b": "green", "c": "aqua"}

    # New game: reset
    teams = teams.merge(2.0, {"d": "pink"})
    assert teams.for_game(2.0) == {"d": "pink"}
    assert teams.for_game(1.0) == {}

    # Outside a game
    teams = teams.merge(None, {"e": "white"})
    assert teams.for_game(None) == {"e": "white"}
