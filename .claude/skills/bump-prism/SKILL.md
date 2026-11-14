---
name: bump-prism
description: This skill should be used when the user asks to "bump prism", "release prism", "cut a prism release", "publish a new prism version", "ship prism vX.Y.Z", or otherwise release a new version of the prism overlay. In this monorepo that also updates the rainbow downloads page (rainbow/) and the flashlight update notice (flashlight/).
---

# Bump Prism Release

Cut a prism overlay release end-to-end in the `Amund211/prism` monorepo. The agent opens PRs, watches CI, merges, tags, downloads artifacts, drafts the GitHub release, verifies it, and opens the post-release PR. One human step: on Windows, run the binary once (SmartScreen) and submit it to Microsoft.

## Why two PRs, in this order

`main` deploys on merge: flashlight (`flashlight-test-and-deploy.yaml`, job `build-and-deploy`) and rainbow (`rainbow-testing.yml`, job `deploy`) go to production when their dirs change on `main`. Prism release binaries come from the `Python testing` run (`testing.yml`) of the push to `main`. So:

1. **Release PR** - changes ONLY `prism/src/prism/__init__.py`. Its push to `main` builds the binaries. No flashlight or rainbow change, so nothing announces the release yet.
2. Tag, draft release, human step, publish.
3. **Post-release PR** - README links, rainbow downloads, flashlight `latestPrism`, dev bump. Merged only after the release is public, so the update notice and the downloads page never point at missing files.

Never put flashlight `latestPrism` or rainbow `DOWNLOADS` changes in the release PR.

## Conventions

- Work in a fresh worktree / checkout of `origin/main`. All paths below are relative to the repo root.
- `<tmp>` = a scratch dir outside the repo (your scratchpad dir). Write `gh` JSON output there and `Read` it; do not pipe network command output.
- One network op per Bash call (`git push`, `gh`, `curl`); no `&&` chains around them. `gh` and `git push`/`fetch` may need to run outside the sandbox.
- Commits that touch `flashlight/` run its `go test` pre-commit hook, which needs Postgres: run that `git commit` outside the sandbox.
- No `--no-verify`. Prism coverage gate is `fail_under=100` (`prism/pyproject.toml`).
- Merge with `gh pr merge <n> --rebase --delete-branch` (each commit lands on `main`, no merge commit).

## Track every step in a TODO list

Before Phase 0, call `TaskCreate` once per item below. Mark each `in_progress` when you start and `completed` when verified. On any abort, leave it `in_progress`, tell the user, and wait. Add sub-tasks for reruns / fix-ups. Phase 8 is gated on a clean list.

1. Phase 0 - preflight.
2. Phase 1 - agree version, headline, tag message; filter changelog.
3. Phase 2 - release PR: open, CI green, merge.
4. Phase 3 - verify release commit, tag, push, watch `main` run to success.
5. Phase 4 - download artifacts, check sizes + attestations, draft release.
6. Phase 5 - HUMAN: SmartScreen warm-up + Microsoft submission.
7. Phase 6 - publish as latest, check asset URLs and "latest release".
8. Phase 7 - post-release PR (4 commits): open, CI green, merge, watch deploys, smoke checks.
9. Phase 8 - final report.
10. Phase 9 - draft the Discord announcement.

## How update notices work

Prism clients (v1.11.1+) poll `https://flashlight.prismoverlay.com/v1/prism-notices` with `X-Prism-Version` and `includeVersionUpdates`. Flashlight decides whether to show "New update available". Re-check with `git log -p -- flashlight/internal/app/prism_notices.go prism/src/prism/flashlight/notices.py` if names below have drifted.

- `flashlight/internal/app/prism_notices.go`:
  - `latestPrism` - **bump every release** (Phase 7).
  - `firstPrismVersionWithoutLocalChecker` = `v1.11.1` - **frozen**. Clients below it have their own checker; never move it.
  - `latestPrismReleaseURL` - `/releases/latest/`, never touch.
  - `versionUpdateNotices()` - the gate (`IsAtLeast` the frozen version, then `UpdateAvailable(latestPrism, !includePatchUpdates)`). Notice: `Severity: SeverityUpdate`, `DurationSeconds: 60`.
- `flashlight/internal/ports/client.go` `knownPrismVersions` - metrics allowlist; must hold `v<X.Y.Z>` and `v<X.Y.(Z+1)>-dev`.
- `flashlight/internal/version/version.go` - `Parse`, `MustParse`, `IsAtLeast`, `UpdateAvailable`. Dev versions (`v1.12.0-dev`) parse and count as older than `v1.12.0`.
- `prism/src/prism/flashlight/notices.py` - the client side.

## Phase 0 - Preflight

ABORT and report on any failure.

1. `git fetch origin`; your checkout is clean and at `origin/main`.
2. Current version: `sed -n '1p' prism/src/prism/__init__.py` → `VERSION_STRING = "vX.Y.Z-dev"` (`v` prefix; allowed chars per `prism/tests/prism/test_version_info.py`).
3. Latest release tag: `git tag -l 'v*' --sort=-v:refname | head -3` (ignore the `flashlight-merge` / `rainbow-merge` tags).
4. `gh auth status`.

## Phase 1 - Version, headline, notes (with the user)

Ask (`AskUserQuestion`): new version (bare semver, e.g. `1.12.0`) and a one-line headline.

Changelog since the last tag, prism only (the monorepo also holds flashlight and rainbow commits):

```bash
git log --no-merges v<PREV>..origin/main --pretty=format:'%h %s' -- prism/ > <tmp>/raw-log.txt
```

Also skim `git log --no-merges v<PREV>..origin/main --pretty=format:'%h %s' -- flashlight/` for server changes users notice (e.g. new data via flashlight); mention them only if user-visible.

DROP: `chore:` (read each; some are user-visible), `refactor:`, `test:`, `ci:`, `style:`, `build:`, non-user `docs:`. KEEP: `feat:`, `fix:`, anything about gameplay, UI, settings, performance, user-visible errors. Group by theme; show the filtered list to the user.

### Tag message

Save to `<tmp>/tag-message.txt`. Hard-wrap ~72 chars, prose paragraphs, no headings, no signoff, `**NOTE:**` callouts allowed:

```
v<X.Y.Z> - <headline>

<paragraph 1: marquee feature for end users>

<paragraph 2: secondary features / fixes>

<paragraph 3: removals / behaviour changes / NOTE: callouts>
```

Example (v1.11.0):

```
v1.11.0 - Cheater + sniper detection

Added cheater + sniper detection using the urchin API (not affiliated).
You are automatically alerted if any player in your game is tagged as a
cheater or sniper. A new column will appear with this information, and
those players will be shown at the top of the list.
Users with their own API key can input this to get private tags.
The requests to urchin are proxied through flashlight.

The overlay now only makes API calls to flashlight, which should
hopefully make it more stable and less sensitive to external outages.

Removed winstreak estimates. (...)
```

**Get explicit approval before continuing.**

## Phase 2 - Release PR

```bash
git switch -c release-v<X.Y.Z> origin/main
```

Edit line 1 of `prism/src/prism/__init__.py`: `VERSION_STRING = "v<X.Y.Z>"` (was `"v<X.Y.Z>-dev"` or an older dev). Do NOT touch `prism/pyproject.toml` `version = "0.1.0"`.

```bash
git add prism/src/prism/__init__.py
```

```bash
git commit -m "chore: Bump version for release"
```

```bash
git push -u origin release-v<X.Y.Z>
```

```bash
gh pr create -R Amund211/prism --base main --head release-v<X.Y.Z> --title "chore: Bump version for release" --body "Release v<X.Y.Z>. The tag is cut from this commit once it lands on main."
```

The diff must be exactly one file. Only `Python testing` (+ linting/CodeQL) should run on the PR; if a flashlight or rainbow workflow runs, the PR touches the wrong files - ABORT.

```bash
gh pr checks <n> -R Amund211/prism --watch
```

When green: `gh pr merge <n> -R Amund211/prism --rebase --delete-branch`, then `git fetch origin`.

## Phase 3 - Tag and wait for the `main` run

Release binaries MUST come from the push-to-`main` run of the merged commit, never from PR artifacts (only `main` runs attest provenance).

### 3.1 Find and check the release commit

```bash
git log --format='%H %s' origin/main -- prism/src/prism/__init__.py > <tmp>/release-commit.txt
```

`Read` it. The first line must be `<sha> chore: Bump version for release`; that is `RELEASE_SHA`. Check:

- `git show --stat --format= <RELEASE_SHA>` lists ONLY `prism/src/prism/__init__.py`.
- `git show <RELEASE_SHA>:prism/src/prism/__init__.py` line 1 is `VERSION_STRING = "v<X.Y.Z>"`.

Any mismatch: ABORT.

### 3.2 Tag and push

```bash
git tag -a v<X.Y.Z> -F <tmp>/tag-message.txt <RELEASE_SHA>
```

```bash
git push origin v<X.Y.Z>
```

Tag pushes do not trigger CI; the build already started on the merge.

### 3.3 Find the run

```bash
gh run list -R Amund211/prism --workflow testing.yml --branch main --event push --limit 20 --json databaseId,headSha,status,conclusion,createdAt > <tmp>/runs.json
```

```bash
jq -r --arg sha "<RELEASE_SHA>" '[.[] | select(.headSha == $sha)] | sort_by(.createdAt) | last | .databaseId' <tmp>/runs.json > <tmp>/run-id.txt
```

`Read` it. Empty / `null`: wait 30 s and list again, at most 3 times; then ABORT ("no `Python testing` push run on `main` for `<RELEASE_SHA>`; check https://github.com/Amund211/prism/actions"). That is `RUN_ID`.

### 3.4 Watch and enforce success

```bash
gh run watch <RUN_ID> -R Amund211/prism --exit-status
```

Then double-check:

```bash
gh run view <RUN_ID> -R Amund211/prism --json status,conclusion,headSha > <tmp>/run-final.json
```

Require `status == "completed"`, `conclusion == "success"`, `headSha == RELEASE_SHA`. Else ABORT and tell the user the run URL (`https://github.com/Amund211/prism/actions/runs/<RUN_ID>`), status and conclusion. The tag is pushed but no release exists. Options: fix on `main` and re-tag (`git push origin :refs/tags/v<X.Y.Z>`, then from 3.1), or rerun a flake (`gh run rerun <RUN_ID> -R Amund211/prism --failed`) - ASK first. The macOS `create-dmg` step retries up to 10x (actions/runner-images#7522); the run can take 20+ min. Do not cancel.

## Phase 4 - Artifacts and draft release

```bash
gh run download <RUN_ID> -R Amund211/prism --dir <tmp>/release-v<X.Y.Z>
```

Expected files (`gh` extracts the zips):

```
<tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-windows-latest/prism-v<X.Y.Z>-windows.exe
<tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-ubuntu-latest/prism-v<X.Y.Z>-linux
<tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-macOS-15/prism-v<X.Y.Z>-mac.dmg
```

`ls -l` all three. Missing: ABORT with the run URL. Sizes:

| File | Floor | Last seen (v1.11.1) | Ceiling |
|---|---|---|---|
| `-windows.exe` | 10 MB | ~17 MB | 40 MB |
| `-mac.dmg` | 15 MB | ~26 MB | 60 MB |
| `-linux` | 20 MB | ~34 MB | 80 MB |

Below the floor: truncated build, ABORT. Above the ceiling: warn, go on.

Check build provenance, one call per file:

```bash
gh attestation verify <tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-ubuntu-latest/prism-v<X.Y.Z>-linux --repo Amund211/prism
```

Each must pass and name `.github/workflows/testing.yml` at `refs/heads/main`. A failure: ABORT.

Confirm the tag is on the remote and points at `RELEASE_SHA`:

```bash
git ls-remote origin refs/tags/v<X.Y.Z>^{} > <tmp>/tag-ref.txt
```

### Release notes

Save to `<tmp>/release-notes.md` (fresh template: `gh release view v1.11.0 -R Amund211/prism --json body`):

```markdown
Have feedback or need support? [Join the discord!](https://discord.gg/k4FGUnEHYg)

## Downloads:

<div align="center">

[![Download for Windows](https://github.com/Amund211/prism/raw/v<X.Y.Z>/prism/media/download_windows.png)][latest-windows-download-link] [![Download for Mac](https://github.com/Amund211/prism/raw/v<X.Y.Z>/prism/media/download_mac.png)][latest-mac-download-link] [![Download for Linux](https://github.com/Amund211/prism/raw/v<X.Y.Z>/prism/media/download_linux.png)][latest-linux-download-link]
[^1] [^2] [^3]

</div>

## <Marquee feature heading>

<paragraph 1 from changelog>

## Other changes

- <bullet>

[^1]: Windows and the Windows logo are registered trademarks of the Microsoft Corporation.

[^2]: macOS and the Apple logo are trademarks of Apple Inc., registered in the U.S. and other countries and regions.

[^3]: Linux is the registered trademark of Linus Torvalds in the U.S. and other countries. Tux is the copyright of Larry Ewing \<<lewing@isc.tamu.edu>\>.

[latest-windows-download-link]: https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-windows.exe
[latest-mac-download-link]: https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-mac.dmg
[latest-linux-download-link]: https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-linux

**Full Changelog**: https://github.com/Amund211/prism/compare/v<PREV>...v<X.Y.Z>
```

The images moved to `prism/media/` in the monorepo; old releases use `media/`. Check one image URL returns 200 before creating the draft.

Create the draft (positional tag, no `--target`):

```bash
gh release create v<X.Y.Z> --repo Amund211/prism --draft --verify-tag --title "v<X.Y.Z> - <headline>" --notes-file <tmp>/release-notes.md <tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-windows-latest/prism-v<X.Y.Z>-windows.exe <tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-ubuntu-latest/prism-v<X.Y.Z>-linux <tmp>/release-v<X.Y.Z>/prism-v<X.Y.Z>-macOS-15/prism-v<X.Y.Z>-mac.dmg
```

```bash
gh release view v<X.Y.Z> -R Amund211/prism --json url > <tmp>/release-url.json
```

## Phase 5 - HUMAN: SmartScreen + Microsoft submission

Tell the user:

> Draft release is ready: `<url>`.
>
> On Windows, download `prism-v<X.Y.Z>-windows.exe` from the draft and run it once. SmartScreen warns the first time: "More info" → "Run anyway".
>
> Submit the same file at https://www.microsoft.com/en-us/wdsi/filesubmission (as a software developer; "incorrectly detected / clean" if Defender flagged it). Note the submission ID.
>
> Reply when both are done, with the submission ID.

WAIT. Do nothing else until the user confirms.

## Phase 6 - Publish and verify

```bash
gh release edit v<X.Y.Z> -R Amund211/prism --draft=false --latest
```

`--latest` is explicit: GitHub must mark this as the latest release. Check it:

```bash
gh release view -R Amund211/prism --json tagName,isDraft,isPrerelease,publishedAt > <tmp>/latest.json
```

(`gh release view` with no tag shows the latest release.) Require `tagName == "v<X.Y.Z>"`, `isDraft == false`, `isPrerelease == false`. Keep `publishedAt` for Phase 7.

HEAD-check the three assets, one call each; each must print `200`:

```bash
curl -fsIL -o /dev/null -w "%{http_code}\n" "https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-windows.exe"
```

(and `-mac.dmg`, `-linux`). Also `https://github.com/Amund211/prism/releases/latest/download/prism-v<X.Y.Z>-linux` must be `200`. Any failure: ABORT before Phase 7.

## Phase 7 - Post-release PR (one PR, four commits)

```bash
git fetch origin
```

```bash
git switch -c post-release-v<X.Y.Z> origin/main
```

**Commit 1 - README download links.** `README.md` at the root is a symlink to `prism/README.md`; edit `prism/README.md`. Bump the three `[latest-*-download-link]` definitions (~line 27) to `v<X.Y.Z>`. Do not touch the shields.io badges or `[latest-release-link]` (`/releases/latest`).

```bash
git add prism/README.md
```

```bash
git commit -m "chore: Update download links"
```

**Commit 2 - rainbow downloads.** In `rainbow/src/routes/downloads.tsx`, prepend three entries to `DOWNLOADS` (the first entry per OS wins). `releasedAt` = `publishedAt` from Phase 6; `version` is bare semver:

```ts
{
    os: "Windows",
    version: "<X.Y.Z>",
    releasedAt: new Date("<publishedAt>"),
    link: "https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-windows.exe",
},
{
    os: "Mac OS",
    version: "<X.Y.Z>",
    releasedAt: new Date("<publishedAt>"),
    link: "https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-mac.dmg",
},
{
    os: "Linux",
    version: "<X.Y.Z>",
    releasedAt: new Date("<publishedAt>"),
    link: "https://github.com/Amund211/prism/releases/download/v<X.Y.Z>/prism-v<X.Y.Z>-linux",
},
```

In `rainbow/src/routes/-downloads.ui.test.tsx`, replace the old version in the three places that name it (`grep -n 'v<PREV>'`: the comment, `"Prism overlay v<PREV>"`, the `releases/download/v<PREV>` check).

```bash
git add rainbow/src/routes/downloads.tsx rainbow/src/routes/-downloads.ui.test.tsx
```

```bash
git commit -m "chore(rainbow): Add v<X.Y.Z> to the downloads page"
```

**Commit 3 - flashlight `latestPrism`.**

- `flashlight/internal/app/prism_notices.go`: `var latestPrism = version.MustParse("v<X.Y.Z>")`. Do not touch `firstPrismVersionWithoutLocalChecker` or `latestPrismReleaseURL`; `git diff` must show only the `latestPrism` line in this file.
- `flashlight/internal/ports/client.go` `knownPrismVersions`: add `"v<X.Y.Z>"` and `"v<X.Y.(Z+1)>-dev"` if missing. Prune old entries only if the user asks. Update `client_test.go` if it asserts on the list.
- `flashlight/internal/app/prism_notices_test.go` (`TestBuildGetPrismNotices`): see below.

```bash
go -C flashlight test ./internal/app/... ./internal/ports/...
```

(Needs Postgres for some packages: run outside the sandbox if it fails to connect.)

```bash
git add flashlight/internal/app/prism_notices.go flashlight/internal/app/prism_notices_test.go flashlight/internal/ports/client.go
```

```bash
git commit -m "chore(flashlight): Bump latestPrism to v<X.Y.Z>"
```

(Outside the sandbox: the hook runs `go test` with Postgres.)

**Commit 4 - dev bump.** `prism/src/prism/__init__.py` line 1: `VERSION_STRING = "v<X.Y.(Z+1)>-dev"`. Always a patch bump, also after a minor release (`v1.12.0` → `v1.12.1-dev`).

```bash
git add prism/src/prism/__init__.py
```

```bash
git commit -m "chore: Bump version in development"
```

**Open, watch, merge.**

```bash
git push -u origin post-release-v<X.Y.Z>
```

```bash
gh pr create -R Amund211/prism --base main --head post-release-v<X.Y.Z> --title "chore: Post-release v<X.Y.Z>" --body-file <tmp>/post-release-body.md
```

Body: one line per commit, and "Merging deploys flashlight (update notice for v<X.Y.Z>) and rainbow (downloads page)."

```bash
gh pr checks <n> -R Amund211/prism --watch
```

All three components' checks must pass (prism tests, flashlight tests + test-instance deploy, rainbow lint/build/UI + preview deploy). Optionally open the rainbow preview URL (PR comment) and check `/downloads`.

```bash
gh pr merge <n> -R Amund211/prism --rebase --delete-branch
```

### After merge: deploys and smoke checks

Find the push runs for the new `origin/main` head (`git fetch origin`, `git rev-parse origin/main`) of `flashlight-test-and-deploy.yaml` and `rainbow-testing.yml` with `gh run list --workflow <file> --branch main --event push`, and `gh run watch <id> --exit-status` each. Both deploy jobs must succeed.

Then, one call each:

```bash
curl -fsS -H "X-User-Id: 00000000-0000-0000-0000-000000000001" -H "X-Prism-Version: v<PREV>" "https://flashlight.prismoverlay.com/v1/prism-notices?includeVersionUpdates=all" -o <tmp>/notices-old.json
```

```bash
curl -fsS -H "X-User-Id: 00000000-0000-0000-0000-000000000002" -H "X-Prism-Version: v<X.Y.Z>" "https://flashlight.prismoverlay.com/v1/prism-notices?includeVersionUpdates=all" -o <tmp>/notices-new.json
```

`notices-old.json` must contain `{"message":"New update available! Click here to download.","url":"https://github.com/Amund211/prism/releases/latest/","severity":"update","duration_seconds":60}`. `notices-new.json` must not (other notices, e.g. wrapped, are fine). Then check `https://prismoverlay.com/downloads` shows v<X.Y.Z> first for each OS.

### `prism_notices_test.go` cases

Each case: `name`, `userID`, `prismVersion`, `updateSelection` (`app.UpdateSelectionNone|Minor|All`), `now`, `want`. All cases share the one `latestPrism`.

- **Replace** the stale cases that name the previous `latestPrism` in their purpose (e.g. `"v<PREV>-dev with selection=all sees update notice for v<PREV>"`, `"... suppresses patch bump to v<PREV>"`, `"v<PREV> with selection=all sees no notice"`) with these:
- Previous version sees the notice:

```go
{
    name:            "v<PREV> with selection=all sees update notice for v<X.Y.Z>",
    userID:          domaintest.NewUUID(t),
    prismVersion:    "v<PREV>",
    updateSelection: app.UpdateSelectionAll,
    now:             defaultTime,
    want: []app.PrismNotice{
        {
            Message:         "New update available! Click here to download.",
            URL:             "https://github.com/Amund211/prism/releases/latest/",
            Severity:        app.SeverityUpdate,
            DurationSeconds: new(60.0),
        },
    },
},
```

- Current version sees none: `prismVersion: "v<X.Y.Z>"`, `want: []app.PrismNotice{}`.
- Patch release only: `v<PREV>` with `app.UpdateSelectionMinor` sees none (`"... suppresses patch bump to v<X.Y.Z>"`).
- Keep `"v1.11.0 (below firstPrismVersionWithoutLocalChecker) is suppressed even with selection=all"`: it documents real client behavior.
- Leave cases that use a version only incidentally (wrapped, unicode user).
- `defaultTime` (June 2024) must stay outside the Dec-Jan wrapped window.

## Phase 8 - Final report

- Release URL; tag URL `https://github.com/Amund211/prism/releases/tag/v<X.Y.Z>`.
- Both PR URLs (release, post-release).
- Attestations verified; release is "latest"; asset HEAD checks (200s).
- Flashlight and rainbow deploys succeeded; smoke-check results.
- Microsoft submission ID.
- Anything that failed or needs manual cleanup; any sandbox errors (path / host denied).

## Phase 9 - Discord announcement (draft only)

For `#announcements` in the Prism Discord. Do NOT post it; give it in a fenced code block. Base it on the approved tag message:

- First line: `Version <X.Y.Z> released @Overlay Updates  <headline>`.
- Lead: 1-3 short sentences on what the marquee feature does for players. Internals only when they explain a visible change.
- Sections only as needed: `Updates`, `Notable Changes`, `Other Changes`, `Minor changes`, `Bugfixes`. Small release: 2-4 lines, no headings.
- One line per item; a short reason when behavior is removed or changed. `NOTE:` for surprises. Credit helpers.
- Casual, light emoticons (`:^)`, `<3`).
- Last line: `https://github.com/Amund211/prism/releases/latest`

Example (v1.10.0):

```
Version 1.10.0 released @Overlay Updates  Lunar Client update Fix
Updates
This update fixes the overlay on the newest version of Lunar Client.

It also adds a setting to disable the overlay in Bedwars duels. The overlay is now disabled by default in Bedwars duels :^)

https://github.com/Amund211/prism/releases/latest
```

Apply the user's changes and remind them to post it.

## Things NOT to touch

| What | Why |
|---|---|
| `prism/pyproject.toml` `version = "0.1.0"` | `uv_build` packaging version, never bumped |
| README shields.io badges, `[latest-release-link]` | Track latest automatically |
| `firstPrismVersionWithoutLocalChecker`, `latestPrismReleaseURL` | Frozen / version-independent |
| Old tags (v1.0.0 - v1.2.1, lightweight), `flashlight-merge`, `rainbow-merge` | History |

## References

- `.github/workflows/testing.yml` (`Python testing`: build matrix, artifact names, attestation on `main`)
- `.github/workflows/flashlight-test-and-deploy.yaml`, `.github/workflows/rainbow-testing.yml` (deploy on push to `main`)
- `prism/tests/prism/test_version_info.py`
- `flashlight/internal/app/prism_notices.go`, `prism_notices_test.go`; `flashlight/internal/ports/client.go`, `prism_notices.go`
- `rainbow/src/routes/downloads.tsx`, `-downloads.ui.test.tsx`
