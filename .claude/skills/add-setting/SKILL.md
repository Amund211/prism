---
name: add-setting
description: Add a new setting to Prism Overlay — schema, validation, settings-page UI, and tests. Use when the user asks to add a setting, expose a value in the settings page, or wire a new config field through the codebase.
---

# Add a setting to Prism Overlay

This skill walks through adding a _new_ setting key end-to-end: schema, validation, persistence, tkinter settings page, and tests. It is **not** for renaming, deleting, or changing the default of an existing setting.

## Step 0 — Re-verify the current state (do this every run)

All paths below are relative to the Python project at `prism/` in the monorepo root.

The constants embedded below (existing section list, file paths, validator helper names) were correct when this skill was written, but the codebase moves. Before asking the user any questions, **read the current state** so you don't show the user a stale list:

1. Read `src/prism/overlay/output/overlay/settings_page.py` and grep for `^class .*Section` to get the canonical list of UI sections. Compare against the list in this skill — if a section was added, removed, or renamed, use the live list when prompting the user.
2. Read `src/prism/overlay/settings.py` and confirm `SettingsDict`, `Settings`, and `fill_missing_settings()` still exist with those names.
3. Read `tests/prism/overlay/test_settings.py` and confirm `make_settings_dict` and `fill_settings_test_cases` still exist.

Line numbers being a few off is fine and expected — do not update the skill for that. Only update the skill at the end if **structural** facts drifted (new/removed section, renamed helper, new file split, new required step).

## Step 1 — Gather requirements

Ask the user the following questions. Accept inline answers from the invocation message if already given. **Always offer numbered defaults plus an "other" escape**.

1. **Setting name** (snake_case, required). Reject if it already exists in `SettingsDict`.

2. **Type** — pick one:
   1. `bool` _(default for toggles)_
   2. `int` (with min/max range)
   3. `float` (with min/max range)
   4. `str` (free-form or UUID/key)
   5. `enum` (str from a fixed set of choices)
   6. `keybind` (Key)
   7. `ordered_multi_select` (tuple of items from a fixed pool)
   8. `nested_dict` (advanced — like `known_nicks` or `rating_configs`)
   9. other (specify)

3. **Default value** (required). For `bool` recommend `True` or `False`; for numerics recommend a sensible mid-range value; for `enum` recommend the most common choice.

4. **Validation constraints**:
   - `int` / `float`: ask for `min` and `max`. Recommend defaults appropriate to the value (e.g. timeouts 1–20, percentages 10–100, thread counts 1–16).
   - `enum`: ask for the allowed-values list.
   - `str`: ask if it must match a pattern (UUID, API key shape, free-form).
   - other types: skip.

5. **Editable in settings page?** **yes** _(default)_ / no.
   - If "no", the setting still gets schema + validation + tests, but no UI section work. (Like `disable_overrideredirect` and `hide_with_alpha`.)

6. **Section** — only ask if editable=yes. Show the live list from Step 0 with numbers, plus:
   - N+1: **new section** → then ask for class name (e.g. `NotificationsSection`) and user-visible label (e.g. `"Notifications"`).

7. **Position in section** — **bottom** _(default)_ / top / after `<existing sibling>`.

8. **Reset-to-default button?** _(numerics only)_ — **yes** _(default for scales)_ / no. Numeric scales in this codebase nearly always pair with a Reset button calling a `clamp_*` helper.

9. **Live preview trace?** — **only recommend yes if the setting affects how rows in the stats preview table are rendered** (column visibility, sort order, rating thresholds, hide-dead-players, decimals, etc.). Things like alpha, hotkeys, autowho, thread counts, discord toggles do **not** affect the preview table → recommend **no**. When in doubt, ask explicitly: "does this change how the stats table looks?"

10. **Depends on another setting being enabled?** — **no** _(default)_ / yes → which one. (e.g. discord sub-toggles depend on `discord_rich_presence`.) If yes, the widget should be disabled when the parent is off, mirroring the discord pattern.

11. **Platform restriction?** — **none** _(default)_ / not on macOS / not on Linux / not on Windows. (autowho and show_on_tab are macOS-disabled; mirror that pattern via `sys.platform` checks at the section's `__init__`.)

12. **Side effects on save?** — **none** _(default)_ / describe. Examples that need handling in `behaviour.update_settings()`: API-key change requires cache clear; hotkey change requires listener restart; thread-count change requires thread-pool resize.

## Step 2 — Implement

Track each of these as a task. Edit one file at a time and verify the change compiles before moving on.

### A. `src/prism/overlay/settings.py`

For every setting, regardless of UI:

1. Add the key to `SettingsDict` (TypedDict) with the right type annotation.
2. Add the field to the `Settings` dataclass with the same type and a sensible default-factory if mutable.
3. Update `Settings.from_dict()` — read the key from `source`.
4. Update `Settings.to_dict()` — include the key in the returned dict.
5. Update `Settings.update_from()` — copy the key.
6. Update `fill_missing_settings()` — add a validation block. Mirror the closest-matching existing block; helpers in this file include `get_boolean_setting()` for bools and inline `isinstance + range` checks for numerics. For complex types, factor a `safe_read_*` helper if one doesn't exist. Set the `settings_updated` flag if you had to substitute a default.

### B. `src/prism/overlay/output/overlay/settings_page.py` _(only if editable=yes)_

Existing sections at the time this skill was last verified (re-check in Step 0):

| #   | Class                   | Label                                   |
| --- | ----------------------- | --------------------------------------- |
| 1   | `SupportSection`        | Support and Feedback                    |
| 2   | `MicrosoftAccountSection` | Microsoft account                     |
| 3   | `UrchinSection`         | Urchin API                              |
| 4   | `GeneralSettingSection` | General Settings                        |
| 5   | `AutoWhoSection`        | AutoWho _(macOS-disabled)_              |
| 6   | `DiscordSection`        | Discord Settings                        |
| 7   | `PerformanceSection`    | Performance Settings                    |
| 8   | `DisplaySection`        | Display Settings _(uses preview trace)_ |
| 9   | `ColumnSection`         | Column Settings                         |
| 10  | `GraphicsSection`       | Graphics                                |
| 11  | `StatsSetting`          | Stats Settings _(uses preview trace)_   |

For an **existing section**:

1. Add the field to the section's local dataclass (search for the dataclass next to the section class).
2. Add the widget construction in the section `__init__` at the requested position. Use the canonical pattern for the chosen type — see `reference.md`.
3. Update the section's `set(values)` method to push the value into the widget variable.
4. Update the section's `get() -> SectionDataclass` method to read the widget variable.
5. If `live_preview_trace=yes`, wire the variable through the `trace_for_preview` callback the section already receives (see `DisplaySection` and `StatsSetting` for the pattern).
6. If `depends_on=<parent>`, mirror the discord sub-toggle pattern: add a callback on the parent toggle that enables/disables this widget.
7. If `platform_restriction`, gate the widget construction behind a `sys.platform` check.

For a **new section**:

1. Define the section dataclass.
2. Define the section class — constructor takes `parent: tk.Misc` and any callbacks (e.g. `trace_for_preview` if applicable). Build a `tk.LabelFrame` with the user-visible label.
3. Implement `set(values)` and `get() -> SectionDataclass`.
4. Instantiate the section in `SettingsPage.__init__` (around the bottom of `__init__`, in a position that matches the section's purpose) and `pack` it into the scrollable frame.
5. Wire it into `SettingsPage.set_content()` — slice the relevant fields out of `Settings` into the section's dataclass and call `section.set(...)`.
6. Wire it into `SettingsPage.on_save()` — call `section.get()`, spread its fields into the new `SettingsDict` being built.

### C. `tests/prism/overlay/test_settings.py`

Always required, even for hidden settings:

1. Update `make_settings_dict()` to accept and pass through the new key with its default.
2. Add cases to `fill_settings_test_cases` covering at minimum:
   - **missing key** → fills in default
   - **wrong type** → falls back to default and sets the updated flag
   - **out-of-range** _(numerics only)_ → clamps or defaults
   - **invalid choice** _(enums only)_ → falls back to default
3. Add a row to `settings_to_dict_cases` exercising the round-trip with a non-default value.

### D. `src/prism/overlay/behaviour.py` _(only if side effects on save)_

Add a diff branch in `update_settings()` that compares old vs new for the new key and runs the requested side effect (cache clear, listener restart, etc.).

### E. Consumer code — out of scope

The actual _use_ of the setting (where in the runtime it gets read) is per-setting business logic and is **not** part of this skill. Tell the user explicitly that they need to wire the consumer themselves, or describe what they want and run it as a separate task.

## Step 3 — Verify

Run all four code-quality tools and the test suite. They must all pass. Run them sandboxed; report any failure verbatim.

```bash
cd prism  # from the repo root
uv run isort --check-only src tests
uv run black --check src tests
uv run flake8 src tests
uv run mypy src
uv run pytest tests/prism/overlay/test_settings.py
```

If isort or black fail, run the same commands without `--check-only` / `--check` to fix. If flake8 or mypy fail, fix the underlying issue — do not silence with `# noqa` or `# type: ignore` unless the user explicitly approves it.

Then run the full test suite once to make sure nothing else broke:

```bash
uv run pytest
```

## Step 4 — Self-update if anything was stale

If during Step 0 you found that the skill's section list, helper names, or file paths were structurally wrong (not just line-number drift), edit `.claude/skills/add-setting/SKILL.md` and `.claude/skills/add-setting/reference.md` (in the repo root) to reflect the current state before declaring done. Tell the user what you updated and why, in one sentence.

## Step 5 — Summarize

Report file-by-file what changed, what test coverage was added, and remind the user about the consumer-code wiring that is still their responsibility.

---

For per-type widget templates and validation snippets, see [reference.md](reference.md).
