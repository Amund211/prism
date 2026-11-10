import gzip
from pathlib import Path

import pytest

from tests.loglines import (
    Candidate,
    extract_candidates,
    main,
    message_regex,
    rate,
    split_logline,
)

REAL_CHAT = "[21:18:04] [Client thread/INFO]: [CHAT] "


@pytest.mark.parametrize(
    "line, expected",
    (
        (
            "[21:18:04] [Client thread/INFO]: [CHAT] §7Bob§7: hi",
            ("[21:18:04] ", "[Client thread/INFO]: [CHAT] ", "§7Bob§7: hi"),
        ),
        (
            "[09:00:00] [Client thread/INFO]: Setting user: Bob",
            ("[09:00:00] ", "[Client thread/INFO]: ", "Setting user: Bob"),
        ),
        (
            "(Client thread) Info [CHAT] Bob has joined (1/8)!",
            ("", "(Client thread) Info [CHAT] ", "Bob has joined (1/8)!"),
        ),
        ("no prefix", None),
        ("[Client thread/INFO]: [CHAT]    ", None),
    ),
)
def test_split_logline(line: str, expected: tuple[str, str, str] | None) -> None:
    assert split_logline(line) == expected


@pytest.mark.parametrize(
    "message, real, matches",
    (
        ("Player1 has joined (1/8)!", "Bob has joined (1/8)!", True),
        ("Player1 has joined (1/8)!", "Bob has joined (2/8)!", False),
        ("§7Player1§7: gg", "§7Bob_2§7: gg", True),
        ("§aMe§7: gg", "§aBob§7: gg", True),
        ("Player1, Player1", "Bob, Bob", True),
        ("Player1, Player1", "Bob, Alice", False),
        ("Player1 hi", "Bob hi there", False),
        ("Players hi", "Bob hi", False),
        ("(1+1) [x]", "(1+1) [x]", True),
    ),
)
def test_message_regex(message: str, real: str, matches: bool) -> None:
    assert bool(message_regex(message).fullmatch(real)) is matches


SOURCE = """\
CHAT = "[Client thread/INFO]: [CHAT] "
LINES = (
    f"{CHAT}Player1 has joined (1/8)!",
    "[10:00:00] [Client thread/INFO]: [CHAT] Player2: hello",
    f"{CHAT}{CHAT} dynamic",
    "Player1",
    f"{CHAT}",
)
"""


def test_extract_candidates() -> None:
    assert extract_candidates(SOURCE) == [
        Candidate(3, "Player1 has joined (1/8)!", None),
        Candidate(4, "Player2: hello", "[10:00:00] [Client thread/INFO]: [CHAT] "),
        Candidate(5, None, None),
    ]


@pytest.mark.parametrize(
    "message, prefix, real, expected",
    (
        ("Bob: hi", None, f"{REAL_CHAT}Bob: hi", "exact message-only"),
        ("Player1: hi", None, f"{REAL_CHAT}Bob: hi", "anonymized message-only"),
        (
            "Player1: hi",
            "[00:00:00] [Client thread/INFO]: [CHAT] ",
            f"{REAL_CHAT}Bob: hi  ",
            "anonymized full-line",
        ),
        (
            "Player1: hi",
            "[Render thread/INFO]: [CHAT] ",
            f"{REAL_CHAT}Bob: hi",
            "anonymized message-only",
        ),
        ("Player1: hi", None, f"{REAL_CHAT}Bob: hi!", None),
        ("Player1: hi", None, "Bob: hi", None),
    ),
)
def test_rate(message: str, prefix: str | None, real: str, expected: str) -> None:
    assert rate(message, prefix, real) == expected


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "test_x.py"
    source.write_text(SOURCE, encoding="utf8")
    gz = tmp_path / "2020-01-01-1.log.gz"
    with gzip.open(gz, "wt", encoding="utf8") as f:
        f.write(f"{REAL_CHAT}Bob has joined (1/8)!\n{REAL_CHAT}§7Bob§7: gg\n")
    latest = tmp_path / "latest.log"
    latest.write_bytes(b"[10:00:00] [Client thread/INFO]: [CHAT] \xa7aAlice: hello\n")
    latest_utf8 = tmp_path / "latest2.log"
    latest_utf8.write_text(f"{REAL_CHAT}Alice: hello\n", encoding="utf8")

    assert main([f"{source}:3={gz}:1", f"{source}:4={latest_utf8}:1"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [
        f"{source}:3 PROVEN anonymized message-only {gz}:1: "
        f"{REAL_CHAT}Bob has joined (1/8)!",
        f"{source}:4 PROVEN anonymized full-line {latest_utf8}:1: "
        f"{REAL_CHAT}Alice: hello",
        "2 proofs: 2 proven, 0 failed",
    ]

    assert (
        main(
            [
                f"{source}:3={gz}:2",
                f"{source}:4={latest}:1",  # Not utf8: decoded as cp1252
                f"{source}:5={gz}:1",
                f"{source}:6={gz}:1",
                f"{source}:3={gz}:9",
                f"{source}:3",
            ]
        )
        == 1
    )
    assert capsys.readouterr().out.splitlines() == [
        f"{source}:3 MISMATCH {gz}:2: {REAL_CHAT}§7Bob§7: gg"
        " | expected: Player1 has joined (1/8)!",
        f"{source}:4 MISMATCH {latest}:1: "
        "[10:00:00] [Client thread/INFO]: [CHAT] §aAlice: hello"
        " | expected: Player2: hello",
        f"{source}:5 BAD PROOF: not a literal logline",
        f"{source}:6 BAD PROOF: no logline on this source line",
        f"{source}:3 BAD PROOF: {gz} has no line 9",
        f"{source}:3 BAD PROOF: expected SRC_FILE:LINE=LOG_FILE:LINE",
        "6 proofs: 0 proven, 6 failed",
    ]
