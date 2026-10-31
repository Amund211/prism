"""
Verify that loglines in the source match real Minecraft loglines

Usage: uv run python -m tests.loglines [--diff BASE | --file PATH | LOGLINE ...]
See tests/CLAUDE.md for the rules this enforces.
"""

import argparse
import ast
import gzip
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import PIPE

from prism.overlay.parsing import CHAT_PREFIXES, CLIENT_INFO_PREFIXES

PREFIXES = CHAT_PREFIXES + CLIENT_INFO_PREFIXES
DEFAULT_LOGS = Path.home() / ".minecraft" / "logs"
SYNTHETIC_MARKER = "# Synthetic:"
# The tests of this tool use fake loglines on purpose
OWN_FILES = {"tests/loglines.py", "tests/test_loglines.py"}

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


def _escape(text: str) -> str:
    # Valid in both Python and Rust (rg) regex. re.escape output is not valid in rg
    return re.sub(r"([\\.+*?()|\[\]{}^$#&~-])", r"\\\1", text)


def _body(message: str, *, rust: bool) -> str:
    """Regex where anonymized names match any username. Rust: no backreferences"""
    parts: list[str] = []
    seen: set[str] = set()
    position = 0
    for match in PLACEHOLDER_REGEX.finditer(message):
        parts.append(_escape(message[position : match.start()]))
        group = f"name_{match.group(1)}"
        if rust:
            parts.append(NAME_PATTERN)
        elif group in seen:
            parts.append(f"(?P={group})")
        else:
            parts.append(f"(?P<{group}>{NAME_PATTERN})")
        seen.add(group)
        position = match.end()
    parts.append(_escape(message[position:]))
    return "".join(parts)


def message_regex(message: str) -> re.Pattern[str]:
    return re.compile(_body(message, rust=False))


def _literal(message: str) -> str:
    return max(PLACEHOLDER_REGEX.split(message)[::2], key=len)


@dataclass(frozen=True)
class Candidate:
    line: int
    message: str | None  # None when the string has formatted values we can't check
    prefix: str | None  # Literal head + prefix, if present in the source
    synthetic: bool


def _comments(source: str) -> dict[int, str]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return {t.start[0]: t.string for t in tokens if t.type == tokenize.COMMENT}


def extract_candidates(source: str) -> list[Candidate]:
    """Find all string literals in the source that look like loglines"""
    tree = ast.parse(source)
    comments = _comments(source)
    lines = source.splitlines()
    parents = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }

    def marked(line: int) -> bool:
        return SYNTHETIC_MARKER in comments.get(line, "")

    def marked_above(line: int) -> bool:
        line -= 1
        while line >= 1 and lines[line - 1].strip().startswith("#"):
            if marked(line):
                return True
            line -= 1
        return False

    def is_synthetic(node: ast.AST) -> bool:
        start, end = getattr(node, "lineno"), getattr(node, "end_lineno")
        if any(marked(n) for n in range(start, end + 1)) or marked_above(start):
            return True
        while not isinstance(node, ast.stmt) and node in parents:
            node = parents[node]
            if marked(node.lineno) or marked_above(node.lineno):  # type: ignore
                return True
        return False

    candidates: list[Candidate] = []
    for node in ast.walk(tree):
        message: str | None
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and not isinstance(parents.get(node), ast.JoinedStr)
        ):
            split = split_logline(node.value)
            if split is None:
                continue
            head, prefix, message = split
            literal_prefix: str | None = head + prefix
        elif isinstance(node, ast.JoinedStr):
            first = node.values[0] if node.values else None
            if not isinstance(first, ast.FormattedValue):
                continue
            name = ast.unparse(first.value).upper()
            if not any(word in name for word in ("CHAT", "PREFIX", "INFO")):
                continue
            rest = node.values[1:]
            if not rest:
                continue
            literal_prefix = None
            if len(rest) == 1 and isinstance(rest[0], ast.Constant):
                message = str(rest[0].value).rstrip()
                if not message:
                    continue
            else:
                message = None
        else:
            continue
        candidates.append(
            Candidate(node.lineno, message, literal_prefix, is_synthetic(node))
        )

    return sorted(candidates, key=lambda c: c.line)


@dataclass(frozen=True)
class Found:
    path: Path
    line_number: int
    line: str
    prefix_matches: bool


def _shape(head: str) -> str:
    return re.sub(r"\d", "0", head)


def _rg_lines(directories: Sequence[Path], patterns: Iterable[str]) -> list[str]:
    """Lines matching any pattern, as `path\\0line_number:line`, sorted"""
    command = ["rg", "-z", "--crlf", "--null", "-n", "-H", "--no-heading"]
    command += ["--no-ignore", "--color", "never"]
    command += ["-g", "*.log", "-g", "*.log.gz", "-g", "*.txt"]
    for pattern in patterns:
        command += ["-e", pattern]
    result = subprocess.run([*command, "--", *map(str, directories)], stdout=PIPE)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"rg failed with exit code {result.returncode}")

    lines = []
    for raw in result.stdout.splitlines():
        try:
            lines.append(raw.decode("utf8"))
        except UnicodeDecodeError:
            lines.append(raw.decode("cp1252", errors="replace"))

    def key(line: str) -> tuple[str, int]:
        path, rest = line.split("\0", 1)
        return path, int(rest.split(":", 1)[0])

    return sorted(lines, key=key)


def search(
    directories: Sequence[Path], queries: Sequence[tuple[str, str | None]]
) -> list[Found | None]:
    """
    Find a real logline for each (message, prefix) query

    Prefer a line where the prefix also matches (digits ignored).
    """
    # rg is a fast prefilter over the (multi-GB) logs. Python then checks exactly
    # A message with a line break can never be one real line
    searchable = [
        i
        for i, (m, _) in enumerate(queries)
        if len(_literal(m)) >= 3 and "\n" not in m and "\r" not in m
    ]
    rg_patterns = (_body(queries[i][0], rust=True) + r"\s*$" for i in searchable)
    lines = _rg_lines(directories, rg_patterns) if searchable else []

    results: list[Found | None] = [None] * len(queries)
    for i in searchable:
        message, prefix = queries[i]
        regex, literal = message_regex(message), _literal(message)
        for line in lines:
            if literal not in line:
                continue
            path, rest = line.split("\0", 1)
            number, real = rest.split(":", 1)
            real = real.rstrip("\r")
            split = split_logline(real)
            if split is None or not regex.fullmatch(split[2]):
                continue
            prefix_matches = prefix is not None and _shape(prefix) == _shape(
                split[0] + split[1]
            )
            current = results[i]
            if current is None or (prefix_matches and not current.prefix_matches):
                results[i] = Found(Path(path), int(number), real, prefix_matches)
            if prefix_matches:
                break
    return results


def added_lines(diff: str) -> dict[str, set[int]]:
    """Map file -> added line numbers from `git diff -U0` output"""
    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and current is not None:
            match = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            assert match is not None
            start, count = int(match.group(1)), int(match.group(2) or 1)
            result.setdefault(current, set()).update(range(start, start + count))
    return {path: lines for path, lines in result.items() if lines}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _diff_candidates(repo: Path, base: str) -> list[tuple[str, str, Candidate]]:
    # Like `base...` but includes the working tree: ignore new commits on base
    merge_base = _git(repo, "merge-base", base, "HEAD").strip()
    changed = added_lines(_git(repo, "diff", "-U0", merge_base, "--", "*.py"))
    for path in _git(
        repo, "ls-files", "--others", "--exclude-standard", "--", "*.py"
    ).split():
        changed[path] = set(
            range(1, len((repo / path).read_text("utf8").splitlines()) + 1)
        )
    return [
        (f"{path}:{c.line}", path, c)
        for path, lines in sorted(changed.items())
        if path not in OWN_FILES and (repo / path).is_file()
        for c in extract_candidates((repo / path).read_text("utf8"))
        if c.line in lines
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, fromfile_prefix_chars="@")
    parser.add_argument("loglines", nargs="*", help="Loglines to check")
    parser.add_argument(
        "--file", action="append", default=[], help="Check all loglines in a file"
    )
    parser.add_argument(
        "--diff", metavar="BASE", help="Check loglines added since BASE"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--logs", type=Path, action="append", help=f"Default: {DEFAULT_LOGS}"
    )
    parser.add_argument(
        "--proof",
        action="append",
        default=[],
        metavar="SRC:LINE=LOG:LINE",
        help="The real logline that a source line was copied from",
    )
    parser.add_argument(
        "--require-proof",
        action="store_true",
        help="Fail for lines that are found by search but have no proof",
    )
    args = parser.parse_args(argv)

    # (location, key for --proof, candidate)
    targets: list[tuple[str, tuple[Path, int] | None, Candidate]] = []
    for i, logline in enumerate(args.loglines):
        split = split_logline(logline)
        if split is None:
            # No known prefix: the argument is the message
            candidate = Candidate(0, logline.rstrip(), None, False)
        else:
            head, prefix, message = split
            candidate = Candidate(0, message, head + prefix, False)
        targets.append((f"arg{i}", None, candidate))
    for file in args.file:
        source = Path(file).read_text("utf8")
        targets.extend(
            (f"{file}:{c.line}", (Path(file).resolve(), c.line), c)
            for c in extract_candidates(source)
        )
    if args.diff is not None:
        targets.extend(
            (location, ((args.repo / path).resolve(), c.line), c)
            for location, path, c in _diff_candidates(args.repo, args.diff)
        )

    failed = 0
    proofs: dict[tuple[Path, int], tuple[Path, int]] = {}
    for proof in args.proof:
        source_ref, _, log_ref = proof.partition("=")
        key = _parse_ref(source_ref)
        targets_here = [c for _, k, c in targets if k == key]
        if not targets_here:
            failed += 1
            print(f"{source_ref} BAD PROOF: no logline on this source line")
        elif targets_here[0].synthetic:
            failed += 1
            print(f"{source_ref} BAD PROOF: line is marked synthetic")
        else:
            log_path, log_line = _parse_ref(log_ref)
            proofs[key] = (log_path, log_line)

    to_search = [
        (i, (c.message, c.prefix))
        for i, (_, ref, c) in enumerate(targets)
        if not c.synthetic and c.message is not None and ref not in proofs
    ]
    results = dict(
        zip(
            (i for i, _ in to_search),
            search(args.logs or [DEFAULT_LOGS], [q for _, q in to_search]),
        )
    )

    proven = found = synthetic = 0
    for i, (location, ref, candidate) in enumerate(targets):
        if candidate.synthetic:
            synthetic += 1
            print(f"{location} SYNTHETIC")
        elif candidate.message is None:
            failed += 1
            print(f"{location} NOT FOUND: not a literal logline. Mark it as synthetic")
        elif ref is not None and ref in proofs:
            log_path, log_line = proofs[ref]
            real = _read_line(log_path, log_line)
            rating = _rate(candidate.message, candidate.prefix, real)
            if rating is None:
                failed += 1
                expected = f" | expected: {candidate.message}"
                print(f"{location} MISMATCH {log_path}:{log_line}: {real}{expected}")
            else:
                proven += 1
                print(f"{location} PROVEN {rating} {log_path}:{log_line}: {real}")
        elif (result := results[i]) is not None:
            kind = "full-line" if result.prefix_matches else "message-only"
            source = f"{result.path}:{result.line_number}"
            if args.require_proof:
                failed += 1
                print(f"{location} FOUND {kind} {source}: {result.line} (no proof)")
            else:
                found += 1
                print(f"{location} FOUND {kind} {source}: {result.line}")
        else:
            failed += 1
            print(f"{location} NOT FOUND: {candidate.message}")

    counts = f"{proven} proven, {found} found, {synthetic} synthetic, {failed} failed"
    print(f"{len(targets)} loglines: {counts}")
    return 1 if failed else 0


def _parse_ref(ref: str) -> tuple[Path, int]:
    path, _, line = ref.rpartition(":")
    return Path(path).expanduser().resolve(), int(line)


def _read_line(path: Path, line_number: int) -> str:
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    lines = data.splitlines()
    if not 1 <= line_number <= len(lines):
        return "<no such line>"
    raw = lines[line_number - 1]
    try:
        return raw.decode("utf8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _rate(message: str, prefix: str | None, real: str) -> str | None:
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


if __name__ == "__main__":
    sys.exit(main())
