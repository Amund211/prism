"""Unit tests of the tab-list reader after the front step: decode, model,
policy B4, snap. The equality with the lab reader on the train fixtures was
checked once by hand (T5 on the tabcap step-1 board)."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from prism.overlay.tabcap.reader import model, read
from prism.overlay.tabcap.reader.decode import (
    CHARS_K,
    KIND_TOKEN,
    TEAM_TOKEN,
    decode,
)
from prism.overlay.tabcap.reader.policy import (
    RowRead,
    has_health,
    policy_b4,
    split_row,
)
from prism.overlay.tabcap.reader.snap import (
    assign,
    cost,
    levenshtein,
    normalized,
    snap,
)
from prism.overlay.tabcap.screenshot import Team


def one_hot(text: str, blank_at: tuple[int, ...] = ()) -> np.ndarray:
    """C x T logits whose best path is text, with blanks at the given steps"""
    ids = [CHARS_K.index(c) + 1 for c in text]
    for t in blank_at:
        ids.insert(t, 0)
    lg = np.zeros((len(CHARS_K) + 1, len(ids)), np.float32)
    lg[ids, np.arange(len(ids))] = 5.0
    return lg


def test_charset() -> None:
    assert len(CHARS_K) == 77
    assert CHARS_K.endswith(" ①②③④⑤⑥⑦⑧⑨⑩")
    assert list(TEAM_TOKEN.values()) == [
        "red",
        "blue",
        "green",
        "yellow",
        "aqua",
        "white",
        "pink",
        "gray",
    ]


@pytest.mark.parametrize(
    "text, blank_at, expected",
    (
        ("", (), ""),
        ("AAb", (), "Ab"),  # repeats merge
        ("AAb", (1,), "AAb"),  # a blank splits a repeat
        ("①ab 3", (0, 0, 6), "①ab 3"),
        ("⑩x", (), "⑩x"),
    ),
)
def test_decode(text: str, blank_at: tuple[int, ...], expected: str) -> None:
    assert decode(one_hot(text, blank_at)) == expected


def test_sidecar() -> None:
    side = json.loads(model.SIDECAR.read_text())
    assert hashlib.sha256(model.MODEL.read_bytes()).hexdigest() == side["sha256"]
    assert side["model"] == model.MODEL.name
    assert side["charset"] == CHARS_K
    assert side["tokens"] == {"team": TEAM_TOKEN, "kind": KIND_TOKEN}
    assert side["crop"]["height"] == 20


def test_model() -> None:
    assert model.session() is model.session()  # loaded once
    crop = np.full((20, 40, 3), 255, np.uint8)
    lg = model.logits(crop)
    assert lg.shape == (len(CHARS_K) + 1, 20)  # T = W / 2
    assert isinstance(model.read(crop), str)


@pytest.mark.parametrize(
    "text, expected",
    (
        ("① Player1 20", ("red", "Player1")),
        ("  ⑧ [MVP+] Player1 3 ", ("gray", "Player1")),
        ("⑨ Player1 20", (None, "Player1")),  # kind token: no team
        ("Player1 ② 20", (None, "Player1")),  # token not first: dropped
        ("① 20", ("red", "20")),  # one word: not health
        ("① Player 1", ("red", "Player")),
        ("", (None, "")),
    ),
)
def test_split_row(text: str, expected: tuple[str | None, str]) -> None:
    assert split_row(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    (
        ("① Player1 20", True),
        ("① Player1 40", True),
        ("① Player1 41", False),
        ("① Player1", False),
        ("20", False),
        # The lab used str.isdigit + int() here, which raises on the token
        ("① Player1 ①", False),
    ),
)
def test_has_health(text: str, expected: bool) -> None:
    assert has_health(text) == expected


def test_policy_b4() -> None:
    rows = [
        RowRead("abcdefgh1", 0, 10),  # NPC: no token, above the team rows
        RowRead("⑩ Spec_1", 0, 20),  # kind token, no NPC name: kept, no team
        RowRead("① Player1 20", 0, 30),
        RowRead("① [VIP] Player2 18", 0, 40),
        RowRead("② Player3 7", 0, 50),
        RowRead("③ Player1 12", 0, 60),  # dup: the first read wins
        RowRead("④ ab 20", 0, 70),  # invalid name
        RowRead("Player4 ⑤", 0, 80),  # token not first: no team
        RowRead("zyxwvuts1", 1, 5),  # NPC name in a column with no team row
    ]
    assert policy_b4(rows) == [
        ("Spec_1", None),
        ("Player1", "red"),
        ("Player2", "red"),
        ("Player3", "blue"),
        ("Player4", None),
        ("zyxwvuts1", None),
    ]


def test_policy_b4_gate() -> None:
    rows = [
        RowRead("① Player1 20", 0, 30),
        RowRead("① Player2 20", 0, 40),
        RowRead("② Player3", 0, 50),  # no health: not a gate row
        RowRead("② ab 20", 0, 60),  # invalid name: not a gate row
    ]
    assert policy_b4(rows) == []
    assert policy_b4([]) == []


@pytest.mark.parametrize(
    "a, b, expected",
    (
        ("", "", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("kitten", "sitting", 3),
        ("Player1", "Player1", 0),
        ("Player1", "player1", 1),
        ("ab", "ba", 2),
    ),
)
def test_levenshtein(a: str, b: str, expected: int) -> None:
    assert levenshtein(a, b) == expected
    assert levenshtein(b, a) == expected


def test_normalized_and_cost() -> None:
    assert normalized("", "") == 0.0
    assert normalized("abcd", "abce") == 0.25
    assert cost("Player1", "Player1") == 0.0
    assert cost("[MVP] Play er1", "Player1") == 0.0
    # Case only: lower-case distance + 0.04 beats 2/7
    assert cost("PLayer1", "player1") == pytest.approx(0.04)
    assert cost("abc", "xyz") == 1.0


def test_assign() -> None:
    c = np.array([[0.0, 0.5], [0.5, 0.1]])
    assert assign(c, 0.34, 0.08) == [(0, 0), (1, 1)]
    # Over max cost
    assert assign(np.array([[0.4]]), 0.34, 0.08) == []
    # No margin to the next-best name of the read
    assert assign(np.array([[0.1, 0.15]]), 0.34, 0.08) == []
    # No margin to the next-best read of the name
    assert assign(np.array([[0.1], [0.15]]), 0.34, 0.08) == []


def test_snap() -> None:
    reads: list[tuple[str, Team | None]] = [
        ("Alpha_1", "red"),
        ("Brav_22", "blue"),
        ("Charlie", None),
    ]
    known = ["Bravo_22", "Alpha_1", "Charlie"]
    # Charlie has no team: not snapped
    assert snap(reads, known) == {"Alpha_1": "red", "Bravo_22": "blue"}
    assert snap(reads, []) == {}
    assert snap(reads[2:], known) == {}


def fake_front(
    monkeypatch: pytest.MonkeyPatch, texts: list[str], tab: bool = True
) -> None:
    rows = [SimpleNamespace(y=4 + 12 * i, x0=2, x1=30, col=0) for i in range(3)]
    regions = [SimpleNamespace(prow=SimpleNamespace(row=r)) for r in rows]
    tab_ = SimpleNamespace(k=1) if tab else None
    monkeypatch.setattr(read, "front", lambda rgb: ("grid", tab_, []))
    monkeypatch.setattr(read, "regions_of", lambda rgb, prows, k: regions)
    reads = iter(texts)
    monkeypatch.setattr(model, "read", lambda crop: next(reads))


def test_read_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    rgb = np.zeros((48, 40, 3), np.uint8)
    fake_front(monkeypatch, ["① Player1 20", "② Player2 20", "② Player3 9"])
    assert read.read_tab(rgb) == [
        ("Player1", "red"),
        ("Player2", "blue"),
        ("Player3", "blue"),
    ]


def test_read_tab_no_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_front(monkeypatch, [], tab=False)
    assert read.read_tab(np.zeros((48, 40, 3), np.uint8)) == []


def test_read_teams(monkeypatch: pytest.MonkeyPatch) -> None:
    image = Image.new("RGB", (40, 48))
    assert read.read_teams(image, []) == {}
    fake_front(monkeypatch, ["① Alpha_1 20", "② Bravo_22 20", "② Charli 9"])
    assert read.read_teams(image, ["Charlie", "Alpha_1", "Alpha_1"]) == {
        "Alpha_1": "red",
        "Charlie": "blue",
    }


def test_read_tab_real_front() -> None:
    # A black image has no tab list
    assert read.read_tab(np.zeros((120, 200, 3), np.uint8)) == []
