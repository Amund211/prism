import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Type, TypeVar


class DatabaseReadError(ValueError):
    """Error raised when failing to read a database"""


class DatabaseDecodeError(ValueError):
    """Error raised when failing to decode a read database"""


class InvalidDatabaseError(ValueError):
    """Error raised when failing to decode a read database"""


def read_databases(database_paths: list[Path]) -> list[dict[str, str]]:
    """Read and parse the list of paths into dicts"""
    databases: list[dict[str, str]] = []
    for path in database_paths:
        if path.suffix != ".json":
            raise DatabaseDecodeError(f"Can only decode json, not '{path.suffix}'")

        try:
            with path.open("r") as f:
                try:
                    database = json.load(f)
                except json.JSONDecodeError as e:
                    raise DatabaseDecodeError(str(e)) from e
        except (FileNotFoundError, OSError) as e:
            raise DatabaseReadError(str(e)) from e

        if not isinstance(database, dict):
            raise InvalidDatabaseError("Nick database must be a mapping")

        if not all(isinstance(key, str) for key in database.keys()):  # pragma: no cover
            raise InvalidDatabaseError("All database keys must be strings")

        if not all(isinstance(value, str) for value in database.values()):
            raise InvalidDatabaseError("All database values must be strings")

        databases.append(database)

    return databases


# Generic type to allow subclassing Settings
DerivedNickDatabase = TypeVar("DerivedNickDatabase", bound="NickDatabase")


@dataclass
class NickDatabase:
    """Class for storing multiple mappings of nick -> uuid"""

    default_database: dict[str, str] = field(init=False)  # The first database
    databases: list[dict[str, str]]
    mutex: threading.Lock = field(
        default_factory=threading.Lock, init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        """Set the .default_database field"""
        assert len(self.databases) > 0, "Must provide at least 1 database"
        self.default_database = self.databases[0]

    @classmethod
    def from_disk(
        cls: Type[DerivedNickDatabase],
        database_paths: list[Path],
        *,
        default_database: dict[str, str],
    ) -> DerivedNickDatabase:
        """Read databases from the given paths and prepend a default database"""
        secondary_databases = read_databases(database_paths)
        return cls([default_database, *secondary_databases])

    def knows(self, nick: str) -> bool:
        """Return True if any of the databases contain the nick"""
        return any(nick in database for database in self.databases)

    def __contains__(self, nick: str) -> bool:
        """Implement `nick in nick_database` with `nick_database.knows(nick)`"""
        return self.knows(nick)

    def denick(self, nick: str) -> str:
        """Return True if any of the databases contain the nick"""
        for database in self.databases:
            if nick in database:
                return database[nick]

        raise ValueError("{nick} is not known by the database")

    def __getitem__(self, nick: str) -> str:
        """Implement `nick_database[nick]` with `nick_database.denick(nick)`"""
        return self.denick(nick)

    def get(self, nick: str) -> str | None:
        """Aquire the lock and return the result if we have it. Otherwise None"""
        with self.mutex:
            if nick in self:
                return self[nick]
            else:
                return None

    def get_default(self, nick: str) -> str | None:
        """Aquire the lock and return the result if we have it in the first database"""
        with self.mutex:
            return self.default_database.get(nick, None)


# Empty nick database for use as default arg
EMPTY_DATABASE = NickDatabase([{}])
