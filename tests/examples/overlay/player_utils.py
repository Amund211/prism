from typing import Literal, overload

from examples.overlay.player import (
    KnownPlayer,
    NickedPlayer,
    PendingPlayer,
    Player,
    Stats,
)


@overload
def make_player(variant: Literal["nick"], username: str = ...) -> NickedPlayer:
    ...


@overload
def make_player(variant: Literal["pending"], username: str = ...) -> PendingPlayer:
    ...


@overload
def make_player(
    variant: Literal["player"] = "player",
    username: str = ...,
    fkdr: float = ...,
    stars: float = ...,
    wlr: float = ...,
    winstreak: int | None = ...,
    winstreak_accurate: bool = ...,
    nick: str | None = ...,
    uuid: str | None = ...,
) -> KnownPlayer:
    ...


def make_player(
    variant: Literal["nick", "pending", "player"] = "player",
    username: str = "player",
    fkdr: float = 0.0,
    stars: float = 1.0,
    wlr: float = 0.0,
    winstreak: int | None = None,
    winstreak_accurate: bool = False,
    nick: str | None = None,
    uuid: str | None = None,
) -> Player:
    if variant == "player":
        return KnownPlayer(
            stars=stars,
            stats=Stats(
                fkdr=fkdr,
                wlr=wlr,
                winstreak=winstreak,
                winstreak_accurate=winstreak_accurate,
            ),
            username=username,
            nick=nick,
            uuid=uuid,
        )
    elif variant == "nick":
        assert nick is None, "Provide the nick as the username"
        return NickedPlayer(nick=username)
    elif variant == "pending":
        return PendingPlayer(username=username)
