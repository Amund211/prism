# Loglines in tests

A logline is a line from a Minecraft log: prefix (timestamp, thread, `[CHAT] `) + message.
Tests with loglines must use real lines from the user's logs, not lines you make up.
Real logs: `~/.minecraft/logs/*.log.gz` and `latest.log` (read only).

## Rules

1. **The message is a literal copy** of a real line, byte for byte: `§` color codes,
   ranks, stars, spaces, punctuation and unicode.
2. **Anonymize names, and make no other change.** Other players become `Player1`, `Player2`, ...
   The own user becomes `Me`. The same real name always gets the same placeholder.
   Do not change server names, map names or chat text that is not a name.
   Do not use other placeholders (`Teammate1`, `Someone1`, random strings). Old tests use
   them, but do not copy them.
3. **The prefix can be synthetic only when the prefix is not the subject of the test**, e.g.
   when you use `f"{CHAT}..."`. If the test is about a prefix or a client log format, the
   full line must be real (the tool reports `FOUND full-line`).
4. **An invented or edited message must have a comment** on the line, on the lines above it,
   or above the block that contains it:
   `# Synthetic: <why>. How: <how it was made>`
   Example: `# Synthetic: count is not a number. How: real join line, "1/8" changed to "a/8"`
5. **Do not put real names in the repo.** Search output shows real names. Anonymize them.

## Workflow

1. Find a real line: `rg -z -n -F 'has joined (' ~/.minecraft/logs | head`.
   Note the log file and line number. This is your proof.
2. Copy the message. Anonymize the names.
3. Give a proof for each logline that you added or changed, and verify all of them:

   ```
   uv run python -m tests.loglines --diff origin/main --require-proof \
       --proof tests/prism/overlay/test_parsing.py:412=~/.minecraft/logs/2024-03-02-1.log.gz:1203
   ```

   A proof is `SOURCE_FILE:LINE=LOG_FILE:LINE`. For many proofs, write one
   `--proof=...` per line in a file in your scratchpad and pass `@that-file`.

   Results:
   - `PROVEN exact|anonymized full-line|message-only`: the proof is correct.
   - `MISMATCH`: the log line is not the same as the source line.
   - `FOUND ... (no proof)`: the tool found a match by search, but you gave no proof.
     Use the file and line it shows as your proof, after you check that it is the line
     you copied.
   - `NOT FOUND`, `BAD PROOF`: fix it.

   The exit code is 1 if a line fails. For each failure, find a real line,
   add a `# Synthetic:` comment, or ask the user for a real sample. Do not make the
   tool pass by other means.

   Other modes: `--file PATH` (all loglines in a file, e.g. for an audit) or loglines as
   arguments. Without `--require-proof`, a search result is enough.
4. **Report** the tool output in your final reply, as a table:

   | file:line | status | proof |
   |---|---|---|
   | test_parsing.py:412 | PROVEN anonymized message-only | 2024-03-02-1.log.gz:1203 |
   | test_parsing.py:418 | SYNTHETIC | `# Synthetic: ...` |

   Also give the summary line from the tool (`N loglines: ...`).

The tool finds literal strings with a known prefix (`CHAT_PREFIXES`, `CLIENT_INFO_PREFIXES`),
and f-strings that start with e.g. `{CHAT}`. An f-string with more formatted values cannot be
verified and must be marked synthetic.
