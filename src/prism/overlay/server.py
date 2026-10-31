import ipaddress
from dataclasses import dataclass
from typing import Literal, Self

ServerKind = Literal["hypixel", "local", "ip", "other", "singleplayer"]


@dataclass(frozen=True, slots=True)
class Server:
    host: str | None  # None for singleplayer
    kind: ServerKind

    @classmethod
    def from_host(cls, host: str) -> Self:
        return cls(host=host, kind=classify_server(host))

    @classmethod
    def singleplayer(cls) -> Self:
        return cls(host=None, kind="singleplayer")


def classify_server(host: str) -> ServerKind:
    host = host.lower()
    if host == "hypixel.net" or host.endswith(".hypixel.net"):
        return "hypixel"

    if host == "localhost":
        return "local"

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "other"

    if ip.is_loopback or ip.is_private:
        return "local"

    return "ip"


def server_is_active(server: Server | None) -> bool:
    """
    Return True if the overlay should be active on the given server

    Unknown servers, local proxies and IP literals (Hypixel or a remote proxy)
    fail open so we don't break the overlay for supported setups.
    """
    if server is None:
        return True

    return server.kind in ("hypixel", "local", "ip")
