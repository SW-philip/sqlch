# Favorites section & collapsible categories

## Goal

In sqlch-gui's Station Library list (`sqlch_gui/ui/station_list.py`), let the
user star stations as favorites (shown in a pinned Favorites section at the
top of the list, in addition to their normal category) and collapse/expand
individual category groups, with both favorite status and collapsed state
persisted across restarts.

Scope: GUI's local library list only. The Discover panel
(`sqlch_gui/ui/discover.py`) is a flat search-results list with no category
grouping and is unaffected. The TUI/CLI are separate codepaths and are left
unchanged.

## Data model (`sqlch_gui/library.py`)

- Each station gains a `"favorite": bool` field, defaulting to `False`. Like
  `group`/`bitrate`/`channels` today, `get_station_list()` backfills it for
  any station missing the key (covers stations added before this feature).
- New `set_favorite(station_id: str, is_favorite: bool) -> bool` — same
  shape as `set_group`/`set_frequency`: find the station, set the field,
  save, return whether it found a match.
- `library.json` gains a top-level `"collapsed_groups": list[str]` (sibling
  of `"stations"`), holding the set of category names currently collapsed.
  Missing key defaults to `[]`.
- New `get_collapsed_groups() -> list[str]` and
  `set_collapsed_groups(names: list[str])` — read/replace that list wholesale
  (the caller owns the in-memory set and persists the full list on each
  toggle, same pattern as `set_group`).

No migration step needed — both new fields are additive and default cleanly
for existing `library.json` files.

## `sqlch_gui/ui/banner.py` — `RibbonBanner`

Add optional collapse support without changing existing callers (Discover's
`RibbonBanner("Browse Categories", gold=True)` stays non-collapsible):

- New constructor params: `collapsible: bool = False`, `collapsed: bool =
  False`, `on_toggle: Callable[[], None] | None = None`.
- When `collapsible`, the label is prefixed with a chevron glyph (`▾ ` when
  expanded, `▸ ` when collapsed) and a `Gtk.GestureClick` is attached over
  the banner's full width; releasing a primary click calls `on_toggle()`.
- New `set_collapsed(collapsed: bool)` updates the chevron glyph. The banner
  does not track its own group name or own the persisted state — it's a
  dumb view; `StationListPanel` owns the collapsed set and calls
  `set_collapsed()` after a toggle.

## `sqlch_gui/ui/station_list.py` — `StationListPanel`

### State

- `self._collapsed_groups: set[str]` — loaded from
  `library.get_collapsed_groups()` in `__init__`.
- `_rows_map` changes shape: `dict[str, list[tuple[Gtk.Box, Gtk.Label,
  EqStrip]]]` — a list per station id instead of a single tuple, since a
  favorited station now has two on-screen rows (Favorites section +
  category group). `set_active()` and `_apply_probe()` iterate the list for
  a given id and update every entry.

### `refresh()`

1. Clear `list_box` and `_rows_map` as today.
2. Load stations, compute `favorites = sorted([s for s in stations if
   s.get("favorite")], key=lambda s: s["name"].lower())`.
3. If `favorites` is non-empty: append a `RibbonBanner("★ Favorites",
   gold=True, collapsible=True, collapsed="★ Favorites" in
   self._collapsed_groups, on_toggle=...)`, then a row (via the shared row
   builder) for each favorite, each row tagged `row._group_name = "★
   Favorites"`.
4. For each category group (existing alphabetical-by-group-name loop):
   append a `RibbonBanner(g_name, collapsible=True, collapsed=g_name in
   self._collapsed_groups, on_toggle=...)`, then rows for that group's
   stations sorted by frequency as today, each row tagged `row._group_name =
   g_name`.
5. Re-apply probed live text / active styling as today, now iterating
   `_rows_map[s_id]` (a list) instead of a single tuple.

### Row construction

Extract the existing per-station row-building block (freq label, body,
mini-eq, tag pennant, click gesture) into `_build_station_row(self, s: dict)
-> Gtk.Box`, used by both the Favorites loop and the category loop so a
favorited station's two rows are genuinely separate widget instances built
from the same code path. Add a star toggle button to the row, placed before
the frequency label:

- `Gtk.Button(icon_name="starred-symbolic" if s.get("favorite") else
  "non-starred-symbolic")`, styled with the existing `.control-btn` class
  (flat icon button already used elsewhere in the app).
- `clicked` handler: `library.set_favorite(s["id"], not
  s.get("favorite")); self.refresh()`. Being a real `Gtk.Button`, GTK's own
  event handling consumes the click before it reaches the row's
  `GestureClick`, so starring never also triggers playback.

### Collapse toggle

`self.on_toggle_group(self, group_name: str)`:
1. Flip membership of `group_name` in `self._collapsed_groups`.
2. `library.set_collapsed_groups(list(self._collapsed_groups))`.
3. `self.list_box.invalidate_filter()` — no full `refresh()` needed, this
   just re-runs the filter predicate below. Also call `banner.set_collapsed()`
   on the specific banner instance so its chevron flips immediately.

### `filter_station_rows` (existing search filter, extended)

Current behavior: banner rows are hidden whenever search text is present;
everything is shown when search text is empty.

New behavior:
- Banner rows: hidden when search text is present (unchanged); always shown
  when search text is empty (unchanged — a collapsed category still shows
  its header so it can be re-expanded).
- Station rows: when search text is empty, hidden if `row._group_name in
  self._collapsed_groups`, else shown (unchanged text-search branch is
  skipped entirely in this case).
- Station rows: when search text is present, run the existing
  text-matching logic unchanged — an active search always overrides
  collapse, so a match inside a collapsed category still surfaces.

## Out of scope

- No favorite/collapse toggle added to the right-click edit popover — the
  star icon and banner chevron are the only entry points, per the approved
  design.
- Discover panel gets no favorite/collapse affordance.
- No reordering of favorites beyond alphabetical; no drag-and-drop.

## Testing

Manual verification in the running app (`sqlch-gui`):
- Star a station from a category group → it appears in a new "★ Favorites"
  section at top, sorted alphabetically, and still appears in its original
  category.
- Unstar the last favorite → Favorites section disappears.
- Collapse a category → its rows hide, header stays with a ▸ chevron;
  expand → rows return, chevron flips back.
- Restart the app → collapsed categories and favorites are unchanged.
- Type into the filter box while a category is collapsed → a match inside
  that category still appears; clear the filter → it collapses again.
- Play a favorited station from either its Favorites row or its category
  row → both rows show the active/eq-strip state; the same is true for
  live-probe title text.
- Click the star button on a row → does not also start playback.
