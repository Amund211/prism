import threading
from dataclasses import dataclass, field
from typing import Optional, Type, TypeVar

# Generic type to allow subclassing Settings
DerivedNickDatabase = TypeVar("DerivedNickDatabase", bound="NickDatabase")


@dataclass
class NickDatabase:
    """Class for storing multiple mappings of nick -> uuid"""

    databases: list[dict[str, str]]
    mutex: threading.Lock = field(
        default_factory=threading.Lock, init=False, compare=False, repr=False
    )

    @classmethod
    def from_disk(
        cls: Type[DerivedNickDatabase], default_database: dict[str, str]
    ) -> DerivedNickDatabase:
        # TODO: read and validate nickdatabases on disk
        return cls([default_database])

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

    def get(self, nick: str) -> Optional[str]:
        """Aquire the lock and return the result if we have it. Otherwise None"""
        with self.mutex:
            if nick in self:
                return self[nick]
            else:
                return None


# Empty nick database for use as default arg
EMPTY_DATABASE = NickDatabase([])
