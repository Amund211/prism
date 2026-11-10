"""
Prove that loglines in the source were copied from real Minecraft loglines

Usage: uv run python -m tests.loglines SRC_FILE:LINE=LOG_FILE:LINE ...
See tests/CLAUDE.md for the rules.
"""

import argparse
import ast
import gzip
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from prism.overlay.parsing import CHAT_PREFIXES, CLIENT_INFO_PREFIXES

PREFIXES = CHAT_PREFIXES + CLIENT_INFO_PREFIXES

# Color codes are word characters, so a plain \b does not work after e.g. §7
PLACEHOLDER_REGEX = re.compile(
    r"(?:(?<=§[0-9a-fklmnor])|(?<![A-Za-z0-9_]))"
    r"(Player\d+|Me|OwnUsername)(?![A-Za-z0-9_])"
)
NAME_PATTERN = r"[A-Za-z0-9_]{1,16}"


def split_logline(line: str) -> tuple[str, str, str] | None:
    """Split a logline into (head, prefix, message). Head is e.g. the timestamp"""
    matches = [(line.find(p), -len(p), p) for p in PREFIXES if p in line]
    if not matches:
        return None
    start, _, prefix = min(matches)
    message = line[start + len(prefix) :].rstrip()
    if not message:
        return None
    return line[:start], prefix, message


def message_regex(message: str) -> re.Pattern[str]:
    """Regex where anonymized names match any username"""
    parts: list[str] = []
    seen: set[str] = set()
    position = 0
    for match in PLACEHOLDER_REGEX.finditer(message):
        parts.append(re.escape(message[position : match.start()]))
        group = f"name_{match.group(1)}"
        if group in seen:
            parts.append(f"(?P={group})")
        else:
            parts.append(f"(?P<{group}>{NAME_PATTERN})")
        seen.add(group)
        position = match.end()
    parts.append(re.escape(message[position:]))
    return re.compile("".join(parts))


@dataclass(frozen=True)
class Candidate:
    line: int
    message: str | None  # None when the string has formatted values we can't check
    prefix: str | None  # Literal head + prefix, if present in the source


def extract_candidates(source: str) -> list[Candidate]:
    """Find all string literals in the source that look like loglines"""
    tree = ast.parse(source)
    in_fstring = {
        id(value)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for value in node.values
    }

    candidates: list[Candidate] = []
    for node in ast.walk(tree):
        message: str | None
        prefix: str | None = None
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in in_fstring
        ):
            split = split_logline(node.value)
            if split is None:
                continue
            head, chat_prefix, message = split
            prefix = head + chat_prefix
        elif isinstance(node, ast.JoinedStr):
            if len(node.values) < 2:
                continue
            first, *rest = node.values
            if not isinstance(first, ast.FormattedValue):
                continue
            name = ast.unparse(first.value).upper()
            if not any(word in name for word in ("CHAT", "PREFIX", "INFO")):
                continue
            if len(rest) == 1 and isinstance(rest[0], ast.Constant):
                message = str(rest[0].value).rstrip()
                if not message:
                    continue
            else:
                message = None
        else:
            continue
        candidates.append(Candidate(node.lineno, message, prefix))

    return sorted(candidates, key=lambda c: c.line)


def _shape(head: str) -> str:
    return re.sub(r"\d", "0", head)


def rate(message: str, prefix: str | None, real: str) -> str | None:
    """Rate how well a real line proves a source line. None if it does not"""
    split = split_logline(real)
    if split is None:
        return None
    head, real_prefix, real_message = split
    if message == real_message:
        kind = "exact"
    elif message_regex(message).fullmatch(real_message):
        kind = "anonymized"
    else:
        return None
    prefix_matches = prefix is not None and _shape(prefix) == _shape(head + real_prefix)
    return f"{kind} {'full-line' if prefix_matches else 'message-only'}"


def _parse_ref(ref: str) -> tuple[Path, int]:
    path, _, line = ref.rpartition(":")
    return Path(path).expanduser(), int(line)


def _read_lines(path: Path) -> list[str]:
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    try:
        return data.decode("utf8").splitlines()
    except UnicodeDecodeError:  # Windows logs are not always utf8
        return data.decode("cp1252", errors="replace").splitlines()


def check(proof: str) -> tuple[bool, str]:
    """Check one proof. Return (ok, report line)"""
    source_ref, _, log_ref = proof.partition("=")
    if not log_ref:
        return False, f"{proof} BAD PROOF: expected SRC_FILE:LINE=LOG_FILE:LINE"
    source_path, source_line = _parse_ref(source_ref)
    log_path, log_line = _parse_ref(log_ref)

    candidates = [
        c
        for c in extract_candidates(source_path.read_text("utf8"))
        if c.line == source_line
    ]
    if not candidates:
        return False, f"{source_ref} BAD PROOF: no logline on this source line"
    candidate = candidates[0]
    if candidate.message is None:
        return False, f"{source_ref} BAD PROOF: not a literal logline"

    lines = _read_lines(log_path)
    if not 1 <= log_line <= len(lines):
        return False, f"{source_ref} BAD PROOF: {log_path} has no line {log_line}"
    real = lines[log_line - 1]

    rating = rate(candidate.message, candidate.prefix, real)
    if rating is None:
        expected = f" | expected: {candidate.message}"
        return False, f"{source_ref} MISMATCH {log_path}:{log_line}: {real}{expected}"
    return True, f"{source_ref} PROVEN {rating} {log_path}:{log_line}: {real}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, fromfile_prefix_chars="@")
    parser.add_argument(
        "proofs",
        nargs="+",
        metavar="SRC_FILE:LINE=LOG_FILE:LINE",
        help="The real logline that a source line was copied from",
    )
    args = parser.parse_args(argv)

    failed = 0
    for proof in args.proofs:
        ok, report = check(proof)
        failed += not ok
        print(report)

    total = len(args.proofs)
    print(f"{total} proofs: {total - failed} proven, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
