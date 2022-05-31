from pathlib import Path
from typing import Type

import pytest

from examples.overlay.nick_database import (
    EMPTY_DATABASE,
    DatabaseDecodeError,
    DatabaseReadError,
    InvalidDatabaseError,
    NickDatabase,
)


def test_empty_database() -> None:
    """Assert properties of the default empty database"""
    assert isinstance(EMPTY_DATABASE, NickDatabase)
    assert len(EMPTY_DATABASE.databases) == 1
    assert len(EMPTY_DATABASE.default_database) == 0


def test_nick_database() -> None:
    """Assert properties of NickDatabases"""
    databases: list[dict[str, str]] = [{}, {}, {}]
    nick_database = NickDatabase(databases)
    nick = "AmazingNick"

    assert nick not in nick_database
    assert not nick_database.knows(nick)
    assert nick_database.get(nick) is None
    assert nick_database.get_default(nick) is None
    with pytest.raises(ValueError):
        nick_database[nick]

    with nick_database.mutex:
        databases[1][nick] = "someuuid"
        assert nick in nick_database
        assert nick_database.knows(nick)

        assert nick_database[nick] == "someuuid"
        assert nick_database.denick(nick) == "someuuid"
    assert nick_database.get(nick) == "someuuid"
    assert nick_database.get_default(nick) is None

    with nick_database.mutex:
        databases[0][nick] = "higherprionick"
        assert nick in nick_database
        assert nick_database.knows(nick)

        assert nick_database[nick] == "higherprionick"
        assert nick_database.denick(nick) == "higherprionick"
    assert nick_database.get(nick) == "higherprionick"
    assert nick_database.get_default(nick) == "higherprionick"


@pytest.mark.parametrize(
    "json_data, obj, exception",
    (
        ("{}", {}, None),
        ('{"AmazingNick": "uuid"}', {"AmazingNick": "uuid"}, None),
        ("malformed json", None, DatabaseDecodeError),
        ('{123: "uuid"}', None, DatabaseDecodeError),  # Keys must be strings
        ('{"AmazingNick": 123}', None, InvalidDatabaseError),
        ("[]", None, InvalidDatabaseError),
        ('""', None, InvalidDatabaseError),
    ),
)
def test_nick_database_from_disk(
    json_data: str,
    obj: dict[str, str] | None,
    exception: Type[ValueError] | None,
    tmp_path: Path,
) -> None:
    assert (obj is None) ^ (exception is None)

    default_database: dict[str, str] = {}

    db_path = tmp_path / "nick_db.json"

    with db_path.open("w") as f:
        f.write(json_data)

    if obj is not None:
        nick_database = NickDatabase.from_disk(
            [db_path], default_database=default_database
        )
        assert nick_database.databases[0] is default_database
        assert nick_database.databases[1] == obj
    elif exception is not None:
        with pytest.raises(exception):
            NickDatabase.from_disk([db_path], default_database=default_database)
    else:
        raise ValueError("Bad params")


def test_nick_database_from_disk_errors(tmp_path: Path) -> None:
    """Assert that appropriate errors are raised in .from_disk"""

    with pytest.raises(DatabaseDecodeError):
        NickDatabase.from_disk([tmp_path / "incorrect.extension"], default_database={})

    with pytest.raises(DatabaseReadError):
        NickDatabase.from_disk([tmp_path / "doesntexist.json"], default_database={})
