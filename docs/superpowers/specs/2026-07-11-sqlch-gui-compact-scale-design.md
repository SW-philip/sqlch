# Compact Player + Library/Discover Scale-Down — Design

**Date:** 2026-07-11
**Status:** Approved

## Summary

Shrink `sqlch_gui`'s whole popup — the Now Playing card, the Library
(station list) rows, and the Discover panel — to roughly 75% of current
scale. Pure sizing/spacing/font pass plus one small aesthetic cleanup (see
"Unstyled entries" below); no layout restructuring, no new widgets, no
behavior changes.

## Why

The window and its controls currently run large relative to what they show.
A visual comparison of the current size against two compact directions
(~75% and ~58%) was reviewed live; the ~75% "Compact" direction was chosen
as tight but still comfortably readable/clickable. The window's overall
footprint shrinks along with its contents (not just internal padding), and
the compact treatment extends to Discover as well as Library, since they
share CSS classes and would look mismatched if only one shrank.

## Scope

### `window.py`

- `self.set_default_size(380, -1)` → `290, -1`.
- `MAX_DRAWER_HEIGHT` 420 → 320 (the ceiling; `_compute_drawer_max` already
  caps further to fit the monitor, unaffected).
- `DRAWER_BOTTOM_GAP` and other drawer-physics constants (spring omega/zeta,
  fling velocity, click slop) are unaffected — those are about motion feel,
  not size.

### `common.py` (global CSS)

Tighten proportionally, roughly one size-step down each:

- `.popup-window`: `border-radius` 16px → 13px; `margin` 3px 14px 14px 3px →
  2px 10px 10px 2px; `padding` 3px → 2px.
- `.sidebar` / `.nav-btn`: padding and margins tightened ~25%; `.nav-btn`
  `border-radius` 8px → 6px.
- `.card`: `padding` 6px → 4px, `border-radius` 12px → 10px.
- `.cover-art`: `min-width`/`min-height` 130px → 98px (matches
  `cover_img.set_pixel_size(130)` → `98` and the back-plate
  `track_scroll.set_size_request(130, 130)` → `(98, 98)` in `now_playing.py`);
  `.cover-glyph` `font-size` 50px → 38px.
- `.corner-tag` family: padding 2px 7px → 2px 5px, `font-size` 0.65em → 0.6em.
- `.list-plate` / `.list-header` / `.station-row`: padding tightened ~20-25%
  (e.g. `.station-row` 5px 8px → 4px 6px, `.list-header` 6px 10px → 5px 8px),
  `border-radius` values step down 2px each.
- `.control-btn`: `min-width`/`min-height` 38px → 28px, `border-radius` 14px
  → 11px. `.control-btn.primary`: 48px → 36px, `border-radius` 17px → 13px.
- Text classes step down one notch: `.meta-title` 1.25em → 1.05em,
  `.meta-artist` 1.0em → 0.88em, `.thread-label` 0.85em → 0.75em,
  `.tech-badge`/`.tag-chip` 0.8em → 0.72em, `.small-badge` 0.7em → 0.65em,
  `.knob-tag` 0.62em → 0.58em, `.brand-tag` 0.6em → 0.56em,
  `.ribbon-label`/`.pennant-label` 0.78em/0.75em → ~0.7em each.
- New `.field-entry` class (see "Unstyled entries" below).

### `controls.py`

- `ThreadSlider`: `set_size_request(-1, 34)` → `(-1, 26)`; internal geometry
  constants (`_MARGIN`, `_NUB_GAP`, `_NUB_ZONE`, `_NUB_RADIUS_X`,
  `_NUB_RADIUS_Y`) and the button `radius`/dimple/pull-line sizes in
  `_on_draw` scale down by the same ~25% factor so the tufted-button
  proportions look identical, just smaller. Exact pixel values tuned live
  during implementation (this is a Cairo draw, easiest to eyeball against
  the running dev instance rather than derive analytically).
- `RecordBubble`: `set_size_request(46, 46)` → `(34, 34)`; the `radius = ...
  - 5.0` inset in `_on_draw` shrinks to `- 4.0` so the ring/bubble proportion
  holds at the smaller size.
- `NavColumn`: spool glyph `set_content_width/height(18)` → `14`.

### `eq_strip.py`

- `NowPlayingPanel`'s big strip: default ctor args `width=90, height=24` →
  `~68, 18` (called with no args in `now_playing.py`, so the default
  changes there).
- Mini per-row strip in `station_list.py`: `EqStrip(n_beads=3, width=22,
  height=14)` → `(n_beads=3, width=18, height=11)`.

### `now_playing.py`

- `cover_img.set_pixel_size(130)` → `98`; `track_scroll.set_size_request(130,
  130)` → `(98, 98)`; `GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 130,
  130, True)` → `(path, 98, 98, True)`.
- `Box`/`text_box` spacing values (currently 3-6px) tightened by ~1-2px each.
- No structural change: flanking nav/art/transport row, eq strip, text
  block, volume row, play button, tech readout stay in the same order and
  relationship — just smaller.

### `station_list.py` / `discover.py`

- Outer margins (`set_margin_*`, currently 8px) → 6px; `Box` spacing
  (currently 6-8px) → 5-6px.
- No filtering/CRUD/search behavior changes — purely sizing.

### Unstyled entries (small included cleanup)

`filter_entry` (Library), `ent_query` (Discover search), and `ent_name`/
`ent_url` (Library's add-station row) are plain `Gtk.Entry` widgets with no
custom CSS class today — they render as default GTK entries, which clash
with the dashed-fabric look everywhere else (only the context-menu's edit
entries currently get `.context-menu entry` styling). Add a shared
`.field-entry` CSS class — dashed border, small `border-radius`, tight
padding, colors matching the surrounding card (`STAGE`/`WING`) — and apply
it to all four entries. Sized to the compact scale from the start (no
separate "before" size to shrink from, since it's new).

## Explicitly out of scope

- `TornSeparator` (the drawer drag-handle seam) — stays near its current
  size. It's an interactive drag target, not an informational field, and
  shrinking it would make it fussier to grab.
- Any structural/layout change — no elements move, reorder, or change
  relationship to each other. Aesthetic (fabric/thread/stitch styling,
  palette usage, hover/press physics) stays identical.
- Discover's genre-tag wording, search behavior, or result-row content.
- Keyboard shortcuts, accessibility changes, or new interactions.

## Testing

No test infrastructure exists in this repo (consistent with prior specs).
Manual verification via the working-tree dev launch flow:

1. Launch the app — window opens noticeably smaller (~290px wide vs
   today's ~380px), Now Playing card content (art, buttons, text, volume,
   readout) all visibly smaller but still legible and clickable.
2. Compare against a screenshot/memory of the current build to confirm nav
   buttons, play button, REC/Stop/Mute, and the volume slider's button/nub
   are all still comfortably clickable at the smaller size, not fiddly.
3. Open Library — drawer caps at the new smaller max-height, rows are
   visibly tighter, filter entry now has the dashed-fabric look instead of
   a plain white box, filtering still works.
4. Open Discover — genre tag grid and search results are equally tighter,
   search entry has the new `.field-entry` look, search/import still work.
5. Confirm across at least two different palette themes (e.g. switch
   `palette.sh` themes) that the new `.field-entry` styling reads correctly
   in both light and dark palettes (uses `SCORE`/`STAGE`/`WING`/thread
   color, not hardcoded hex, consistent with the existing color-rule
   convention).
6. Confirm the drawer spring-snap animation and seam drag still feel the
   same (untouched by this change) at the new smaller drawer max-height.
