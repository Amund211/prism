import pytest

from examples.sidelay.nick_database import EMPTY_DATABASE, NickDatabase


def test_empty_database() -> None:
    """Assert properties of the default empty database"""
    assert isinstance(EMPTY_DATABASE, NickDatabase)
    assert len(EMPTY_DATABASE.databases) == 0


def test_nick_database() -> None:
    """Assert properties of NickDatabases"""
    databases: list[dict[str, str]] = [{}, {}, {}]
    nick_database = NickDatabase(databases)
    nick = "AmazingNick"

    assert nick not in nick_database
    assert not nick_database.knows(nick)
    assert nick_database.get(nick) is None
    with pytest.raises(ValueError):
        nick_database[nick]

    with nick_database.mutex:
        databases[1][nick] = "someuuid"
        assert nick in nick_database
        assert nick_database.knows(nick)

        assert nick_database[nick] == "someuuid"
        assert nick_database.denick(nick) == "someuuid"
    assert nick_database.get(nick) == "someuuid"

    with nick_database.mutex:
        databases[0][nick] = "higherprionick"
        assert nick in nick_database
        assert nick_database.knows(nick)

        assert nick_database[nick] == "higherprionick"
        assert nick_database.denick(nick) == "higherprionick"
    assert nick_database.get(nick) == "higherprionick"


def test_nick_database_from_disk() -> None:
    """Assert properties of NickDatabase.from_disk"""
    default_database: dict[str, str] = {}
    nick_database = NickDatabase.from_disk(default_database=default_database)
    assert nick_database.databases[0] is default_database
