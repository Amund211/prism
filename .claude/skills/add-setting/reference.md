# Reference snippets for `add-setting`

Paths are relative to the Python project at `prism/`. Canonical patterns lifted from the live codebase. **Re-read the source files before copying** — these are accurate at the time of writing but the codebase moves. Use these as templates, not as drop-in code.

## Validation in `fill_missing_settings`

Pick the closest template by type. The function returns `tuple[SettingsDict, bool]` where the bool is `settings_updated`. Always set `settings_updated = True` (or use `|=`) when you substitute a default.

### bool

```python
my_setting, settings_updated = get_boolean_setting(
    incomplete_settings, "my_setting", settings_updated, default=True
)
```

### int with range (clamp+default on bad input)

```python
my_setting = incomplete_settings.get("my_setting", None)
if not isinstance(my_setting, int) or not MIN <= my_setting <= MAX:
    settings_updated = True
    my_setting = DEFAULT
```

### float with range

```python
my_setting = incomplete_settings.get("my_setting", None)
if not isinstance(my_setting, (int, float)) or not MIN <= my_setting <= MAX:
    settings_updated = True
    my_setting = DEFAULT
my_setting = float(my_setting)
```

### str from a fixed enum

```python
my_setting = incomplete_settings.get("my_setting", None)
if my_setting not in ALLOWED_VALUES:  # ALLOWED_VALUES is a frozenset/tuple
    settings_updated = True
    my_setting = DEFAULT
```

### Optional UUID/key (None when unset is valid)

```python
my_key = incomplete_settings.get("my_key", None)
if my_key is not None and (not isinstance(my_key, str) or not is_uuid(my_key)):
    settings_updated = True
    my_key = None
```

### keybind

```python
my_keybind, my_keybind_updated = construct_key_dict(
    incomplete_settings.get("my_keybind", None), default=DEFAULT_KEY_DICT
)
settings_updated |= my_keybind_updated
```

### tuple from a fixed pool (like column_order)

```python
raw = incomplete_settings.get("my_list", None)
if isinstance(raw, (list, tuple)):
    my_list = tuple(filter(is_valid_item, raw))
    settings_updated |= len(raw) != len(my_list)
else:
    my_list = ()
if not my_list:
    my_list = DEFAULT_LIST
    settings_updated = True
```

## Widget patterns in a section's `__init__`

All sections grid widgets into `self.frame` (a `tk.LabelFrame` from `parent.make_section(label)`). Keep `column=0` for labels, `column=1` for the input, and `column=2` for an optional Reset button. Increment `row` for each setting.

Always call `parent.make_widgets_scrollable(label, widget, ...)` after gridding so mouse-wheel scrolling works.

### Boolean toggle

```python
my_label = tk.Label(
    self.frame,
    text="My setting: ",
    font=("Consolas", 12),
    foreground="white",
    background="black",
)
my_label.grid(row=ROW, column=0, sticky=tk.E)
self.my_setting_toggle = ToggleButton(self.frame)
self.my_setting_toggle.button.grid(row=ROW, column=1)
parent.make_widgets_scrollable(my_label, self.my_setting_toggle.button)
```

Read in `get`: `self.my_setting_toggle.enabled`. Write in `set`: `self.my_setting_toggle.set(value)`.

### Boolean toggle that gates a child widget

Add a `toggle_callback` that enables/disables the dependent widget. See `disable_keybind_selector` and `disable_include_patch_updates_toggle` in `GeneralSettingSection` for the full pattern.

```python
def disable_child(enabled: bool) -> None:
    self.child_widget.config(
        state=tk.NORMAL if enabled else tk.DISABLED,
        cursor="hand2" if enabled else "arrow",
    )

self.parent_toggle = ToggleButton(self.frame, toggle_callback=disable_child)
```

### Numeric scale with Reset button

```python
my_label = tk.Label(self.frame, text="My value: ", font=("Consolas", 12),
                   foreground="white", background="black")
my_label.grid(row=ROW, column=0, sticky=tk.E)

self.my_variable = tk.IntVar(value=DEFAULT)  # tk.DoubleVar for float
my_scale = tk.Scale(
    self.frame,
    from_=MIN,
    to=MAX,
    orient=tk.HORIZONTAL,
    length=200,
    foreground="white",
    background="black",
    variable=self.my_variable,
)
my_scale.grid(row=ROW, column=1)

reset_button = tk.Button(
    self.frame,
    text="Reset",
    font=("Consolas", 14),
    foreground="white",
    background="black",
    command=functools.partial(self.my_variable.set, DEFAULT),
    relief="flat",
    cursor="hand2",
)
reset_button.grid(row=ROW, column=2)

parent.make_widgets_scrollable(my_label, my_scale, reset_button)
```

Pair with a `clamp_my_value` method on the section and call it in `get()` to enforce the range when persisting:

```python
def clamp_my_value(self, value: int) -> int:
    return min(MAX, max(MIN, value))
```

### Dropdown / OptionMenu

```python
my_label = tk.Label(self.frame, text="My choice: ", font=("Consolas", 12),
                   foreground="white", background="black")
my_label.grid(row=ROW, column=0, sticky=tk.E)

self.my_variable = tk.StringVar(value="")
# trace_for_preview(self.my_variable)  # only if it affects the stats table
self.my_menu = tk.OptionMenu(self.frame, self.my_variable, *CHOICES)
self.my_menu.grid(row=ROW, column=1)
parent.make_widgets_scrollable(my_label, self.my_menu)
```

In `get()`, validate the result before returning — `tk.StringVar.get()` returns `str`, so re-check it's still in `CHOICES` and fall back if not (mirror `DisplaySection.get` which validates `sort_order` against `str_is_column_name`).

### String entry

```python
self.my_variable = tk.StringVar()
self.my_entry = tk.Entry(self.frame, textvariable=self.my_variable, ...)
```

For sensitive values (API keys), see `UrchinSection` which adds Show/Paste/Clear buttons and masks the value.

### Keybind selector

```python
self.my_keybind_selector = KeybindSelector(self.frame)
self.my_keybind_selector.button.grid(row=ROW, column=1)
```

Read: `self.my_keybind_selector.key`. Write: `self.my_keybind_selector.set_key(key)`.

### Live preview trace (only for stats-table settings)

After creating the `tk.Variable`, call the `trace_for_preview` callback the section was constructed with:

```python
self.my_variable = tk.StringVar(value="")
trace_for_preview(self.my_variable)
```

Recommend this **only** for settings that change how rows render in the stats preview table — column visibility, sort order, hide-dead-players, rating thresholds, decimal counts. Do **not** trace for hotkeys, alpha, autowho timing, thread counts, or discord toggles.

## Section dataclass + class skeleton (new section)

```python
@dataclass(frozen=True, slots=True)
class MySectionSettings:
    """Settings for the MySection"""

    my_setting: bool
    my_other: int


class MySection:  # pragma: nocover
    def __init__(
        self,
        parent: "SettingsPage",
        # trace_for_preview: Callable[[tk.Variable], None] = lambda _v: None,
    ) -> None:
        self.frame = parent.make_section("My Section")
        self.frame.columnconfigure(0, weight=0)

        # ... widgets ...

    def set(self, settings: MySectionSettings) -> None:
        """Set the state of this section"""
        self.my_setting_toggle.set(settings.my_setting)
        self.my_other_variable.set(settings.my_other)

    def get(self) -> MySectionSettings:
        """Get the state of this section"""
        return MySectionSettings(
            my_setting=self.my_setting_toggle.enabled,
            my_other=self.clamp_my_other(self.my_other_variable.get()),
        )
```

Then in `SettingsPage.__init__`, instantiate and pack into the scrollable frame next to the existing sections. Wire it into both `set_content(settings)` (push-down) and `on_save()` (pull-up + spread into the new `SettingsDict`).

## Tests

In `tests/prism/overlay/test_settings.py`:

### `make_settings_dict` factory — add the new key with a default

```python
def make_settings_dict(
    ...,
    my_setting: bool = True,
    ...,
) -> SettingsDict:
    return {
        ...,
        "my_setting": my_setting,
        ...,
    }
```

### `fill_settings_test_cases` — add at minimum these cases

```python
# missing key -> default
({"...other keys...": ...}, make_settings_dict(my_setting=DEFAULT), True),

# wrong type -> default
({"my_setting": "not a bool", ...}, make_settings_dict(my_setting=DEFAULT), True),

# (numerics only) out of range -> clamp/default
({"my_setting": 999, ...}, make_settings_dict(my_setting=DEFAULT), True),

# (enums only) invalid choice -> default
({"my_setting": "nonsense", ...}, make_settings_dict(my_setting=DEFAULT), True),
```

### `settings_to_dict_cases` — round-trip with a non-default value

Add a Settings instance with `my_setting` set to a non-default value, paired with the matching SettingsDict.

## Side-effect handling in `behaviour.update_settings`

If saving the setting needs special handling (cache clear, listener restart, etc.), add a diff branch:

```python
if old_settings.my_setting != new_settings["my_setting"]:
    # do the side effect
    ...
```

Look at the existing `api_key` and `known_nicks` branches in `update_settings` for patterns.
