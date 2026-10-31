import gzip
import os
import subprocess
from pathlib import Path

import pytest

from tests.loglines import (
    Candidate,
    added_lines,
    extract_candidates,
    main,
    message_regex,
    search,
    split_logline,
)

REAL_CHAT = "[21:18:04] [Client thread/INFO]: [CHAT] "


@pytest.mark.parametrize(
    "line, head, prefix, message",
    (
        (
            "[21:18:04] [Client thread/INFO]: [CHAT] §7Bob§7: hi",
            "[21:18:04] ",
            "[Client thread/INFO]: [CHAT] ",
            "§7Bob§7: hi",
        ),
        (
            "[09:00:00] [Client thread/INFO]: Setting user: Bob",
            "[09:00:00] ",
            "[Client thread/INFO]: ",
            "Setting user: Bob",
        ),
        (
            "(Client thread) Info [CHAT] Bob has joined (1/8)!",
            "",
            "(Client thread) Info [CHAT] ",
            "Bob has joined (1/8)!",
        ),
        ("trailing space   ", None, None, None),
    ),
)
def test_split_logline(
    line: str, head: str | None, prefix: str | None, message: str | None
) -> None:
    result = split_logline(line)
    if head is None:
        assert result is None
    else:
        assert result == (head, prefix, message)


@pytest.mark.parametrize(
    "message, real, matches",
    (
        ("Player1 has joined (1/8)!", "Bob has joined (1/8)!", True),
        ("Player1 has joined (1/8)!", "Bob has joined (2/8)!", False),
        ("§7Player1§7: gg", "§7Bob_2§7: gg", True),
        ("§aMe§7: gg", "§aBob§7: gg", True),
        ("Player1, Player1", "Bob, Bob", True),
        ("Player1, Player1", "Bob, Alice", False),
        ("Player1 hi", "Bob hi ", True),  # Trailing whitespace is stripped
        ("Player1 hi", "Bob hi there", False),
        ("Players hi", "Bob hi", False),
        ("(1+1) [x]", "(1+1) [x]", True),
    ),
)
def test_message_regex(message: str, real: str, matches: bool) -> None:
    assert bool(message_regex(message).fullmatch(real.rstrip())) is matches


SOURCE = """\
CHAT = "[Client thread/INFO]: [CHAT] "
LINES = (
    f"{CHAT}Player1 has joined (1/8)!",
    "[10:00:00] [Client thread/INFO]: [CHAT] Player2: hello",
    # Synthetic: Count is not a number. How: edited real join line
    f"{CHAT}Player1 has joined (a/8)!",
    f"{CHAT}Player1 wat",  # Synthetic: made up. How: typed it
    "Player1",
    f"{CHAT}",
)

# Synthetic: invalid lines. How: random text
BAD = (
    f"{CHAT}aaa",
    f"{CHAT}bbb",
)
"""


def test_extract_candidates() -> None:
    assert extract_candidates(SOURCE) == [
        Candidate(3, "Player1 has joined (1/8)!", None, False),
        Candidate(
            4, "Player2: hello", "[10:00:00] [Client thread/INFO]: [CHAT] ", False
        ),
        Candidate(6, "Player1 has joined (a/8)!", None, True),
        Candidate(7, "Player1 wat", None, True),
        Candidate(14, "aaa", None, True),
        Candidate(15, "bbb", None, True),
    ]


def test_main_dynamic(
    tmp_path: Path, logs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "test_x.py"
    source.write_text('CHAT = "x"\nA = f"{CHAT}{CHAT} hi"\n', encoding="utf8")

    assert main(["--logs", str(logs_dir), "--file", str(source)]) == 1
    assert "2 NOT FOUND: not a literal logline" in capsys.readouterr().out


def write_gz(path: Path, lines: list[str]) -> None:
    with gzip.open(path, "wt", encoding="utf8") as f:
        f.write("\n".join(lines) + "\n")


@pytest.fixture
def logs_dir(tmp_path: Path) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir()
    write_gz(
        logs / "2020-01-01-1.log.gz",
        [f"{REAL_CHAT}Bob has joined (1/8)!", f"{REAL_CHAT}§7Bob§7: gg"],
    )
    (logs / "latest.log").write_text(
        "[10:00:00] [Client thread/INFO]: [CHAT] Alice: hello\n", encoding="utf8"
    )
    return logs


def test_search(logs_dir: Path) -> None:
    joined, full, other_prefix, missing, gg, too_short = search(
        [logs_dir],
        [
            ("Player1 has joined (1/8)!", None),
            ("Player2: hello", "[11:11:11] [Client thread/INFO]: [CHAT] "),
            ("Player2: hello", "[Render thread/INFO]: [CHAT] "),
            ("Player1 has joined (2/8)!", None),
            ("§7Player1§7: gg", None),
            ("Player1", None),
        ],
    )

    assert joined is not None
    assert joined.path.name == "2020-01-01-1.log.gz"
    assert joined.line_number == 1
    assert not joined.prefix_matches

    assert full is not None
    assert full.path.name == "latest.log"
    assert full.prefix_matches
    assert full.line == "[10:00:00] [Client thread/INFO]: [CHAT] Alice: hello"

    assert other_prefix is not None
    assert not other_prefix.prefix_matches

    assert missing is None
    assert gg is not None and gg.line_number == 2
    assert too_short is None

    assert search([logs_dir], [("Bob has\r\njoined", None)]) == [None]


def test_search_prefers_matching_prefix(tmp_path: Path) -> None:
    (tmp_path / "a.log").write_text(
        "(Client thread) Info [CHAT] Bob: hi\r\n"
        "[10:00:00] [Client thread/INFO]: [CHAT] Bob: hi\r\n"
        "[10:00:00] [Client thread/INFO]: [CHAT] (1+1)*? [x] {2} ^$|.#&~- \\d\r\n",
        encoding="utf8",
    )
    (found,) = search([tmp_path], [("(1+1)*? [x] {2} ^$|.#&~- \\d", None)])
    assert found is not None and found.line_number == 3

    (found,) = search([tmp_path], [("Player1: hi", "[Client thread/INFO]: [CHAT] ")])
    assert found is not None
    assert found.line_number == 1
    assert not found.prefix_matches

    (found,) = search(
        [tmp_path], [("Player1: hi", "[00:00:00] [Client thread/INFO]: [CHAT] ")]
    )
    assert found is not None
    assert found.line_number == 2
    assert found.line == "[10:00:00] [Client thread/INFO]: [CHAT] Bob: hi"


def test_added_lines() -> None:
    diff = """\
diff --git a/tests/a.py b/tests/a.py
--- a/tests/a.py
+++ b/tests/a.py
@@ -3,0 +4,2 @@ x
+one
+two
@@ -10 +12 @@ y
+three
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,2 +0,0 @@
-gone
"""
    assert added_lines(diff) == {"tests/a.py": {4, 5, 12}}


def test_main_file(
    tmp_path: Path, logs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "test_x.py"
    source.write_text(SOURCE, encoding="utf8")

    assert main(["--logs", str(logs_dir), "--file", str(source)]) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(f"{source}:3 FOUND message-only ")
    assert out[1].startswith(f"{source}:4 FOUND full-line ")
    assert out[2] == f"{source}:6 SYNTHETIC"
    assert out[3] == f"{source}:7 SYNTHETIC"
    assert out[-1] == "6 loglines: 0 proven, 2 found, 4 synthetic, 0 failed"


def test_main_proof(
    tmp_path: Path, logs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "test_x.py"
    source.write_text(SOURCE, encoding="utf8")
    gz = logs_dir / "2020-01-01-1.log.gz"
    args = ["--logs", str(logs_dir), "--file", str(source)]

    assert main([*args, "--proof", f"{source}:3={gz}:1"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == (
        f"{source}:3 PROVEN anonymized message-only {gz}:1: "
        f"{REAL_CHAT}Bob has joined (1/8)!"
    )
    assert out[1].startswith(f"{source}:4 FOUND full-line ")
    assert out[-1] == "6 loglines: 1 proven, 1 found, 4 synthetic, 0 failed"

    # Without proof, a search result is not enough
    assert main([*args, "--require-proof", "--proof", f"{source}:3={gz}:1"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[1].startswith(f"{source}:4 FOUND full-line ")
    assert out[1].endswith(" (no proof)")
    assert out[-1] == "6 loglines: 1 proven, 0 found, 4 synthetic, 1 failed"

    # Wrong log line
    assert main([*args, "--proof", f"{source}:3={gz}:2"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == (
        f"{source}:3 MISMATCH {gz}:2: {REAL_CHAT}§7Bob§7: gg"
        " | expected: Player1 has joined (1/8)!"
    )

    # Proof that does not point at a logline
    assert main([*args, "--proof", f"{source}:5={gz}:1"]) == 1
    assert capsys.readouterr().out.splitlines()[0] == (
        f"{source}:5 BAD PROOF: no logline on this source line"
    )

    # Proof for a synthetic line
    assert main([*args, "--proof", f"{source}:6={gz}:1"]) == 1
    assert f"{source}:6 BAD PROOF: line is marked synthetic" in capsys.readouterr().out


def test_main_proof_exact_and_full_line(
    tmp_path: Path, logs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "test_x.py"
    source.write_text(
        'A = "[10:00:00] [Client thread/INFO]: [CHAT] Alice: hello"\n',
        encoding="utf8",
    )
    latest = logs_dir / "latest.log"
    proof = f"{source}:1={latest}:1"
    assert main(["--logs", str(logs_dir), "--file", str(source), "--proof", proof]) == 0
    assert f"{source}:1 PROVEN exact full-line {latest}:1: " in capsys.readouterr().out


def test_main_strings(logs_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--logs", str(logs_dir)]
    assert main([*args, f"{REAL_CHAT}§7Player1§7: gg"]) == 0
    assert "FOUND full-line" in capsys.readouterr().out

    assert main([*args, f"{REAL_CHAT}nope"]) == 1
    assert "NOT FOUND" in capsys.readouterr().out

    assert main([*args, "Player1 has joined (1/8)!"]) == 0
    assert "FOUND message-only" in capsys.readouterr().out


def test_main_diff(
    tmp_path: Path,
    logs_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pre-commit sets e.g. GIT_INDEX_FILE, which would point git at the outer repo
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)

    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q")
    git("config", "commit.gpgsign", "false")
    source = repo / "test_x.py"
    source.write_text('CHAT = "x"\nA = f"{CHAT}aaa"\n', encoding="utf8")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    source.write_text(
        'CHAT = "x"\nA = f"{CHAT}aaa"\nB = f"{CHAT}Player1 has joined (1/8)!"\n',
        encoding="utf8",
    )

    assert main(["--logs", str(logs_dir), "--diff", "HEAD", "--repo", str(repo)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("test_x.py:3 FOUND")
    assert out[-1] == "1 loglines: 0 proven, 1 found, 0 synthetic, 0 failed"
