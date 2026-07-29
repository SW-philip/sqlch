# Now Playing Card Redesign — Stacked Deck

**Date:** 2026-07-29
**Status:** Approved

## Summary

Remove the cover-art/tracklist flip-card mechanic and replace it with a
stacked layout: a larger square album art panel spans the card's full
width, title/artist/genre text sits in its own row directly beneath it,
and the tracklist renders in a fixed-height scrolling panel below that —
all simultaneously visible, no flip interaction. The window keeps its
current fixed width (`290px`) and grows taller to fit; it's already
anchored top+right via layer-shell, so vertical growth is the natural
direction (see `window.py:28-33`).

## Why

The user felt the popup was "too sparse" and wanted the album art bigger
and more prominent while still being able to see the album's tracklist.
The actual cause: cover art and tracklist are two faces of the same
98×98px flip-card (`deck_stack` in `now_playing.py`, introduced by
`2026-07-03-album-tracklist-design.md` and left untouched by the
2026-07-25 merged-deck pass) — whichever face is showing, the other is
completely hidden, and both are cramped into a 98px box regardless.
Enlarging or padding either face in isolation doesn't fix the underlying
problem: the two can't be seen together. Three layout directions (stacked
art-over-list, side-by-side art-and-list, or keeping the flip but simply
bigger) were reviewed via the visual companion; stacked was chosen
because it shows both permanently, keeps the window's width (and
therefore the seam/drawer-width math) untouched, and fits the existing
top-anchored growth pattern better than widening would.

This supersedes the "Art + text row" layout from
`2026-07-25-now-playing-merged-deck-design.md` (art inline left, text to
its right) and retires the flip mechanic that spec explicitly left
untouched.

## Layout

Rows inside the `.card` patch, top to bottom (nav row and control row
unchanged from the 2026-07-25 pass):

**1. Nav row** — unchanged.

**2. Album art** — square, scales to the card's full inner width
(roughly 98px → ~220px depending on final margins; tune live rather than
derive analytically, consistent with prior control-widget specs). No
longer paired with a flip-corner tag or wrapped in a rotating
`album-deck-wrapper` — the -3°/2° tilt transform and the
flip-to-tracklist corner icon are both dropped; the art sits flat,
un-rotated. `cover_stack` (placeholder glyph vs. real art) stays as-is,
just resized (`set_pixel_size`, the `GdkPixbuf.new_from_file_at_scale`
call in `_apply_cover_path`, and the `.cover-art` CSS `min-width`/
`min-height` all move from `98` to the new size together).

Corner tags stay on the art, same three positions as today:
- LIVE — top-left
- format — top-right
- REC — bottom-left

**3. Title/artist/genre text** — moves to its own full-width row
directly below the art (previously beside it). `EqStrip` stays behind
the text via the same `Gtk.Overlay` + `set_measure_overlay` pattern
already in place, just re-laid-out horizontally under the art instead of
to its right.

**4. Tracklist** — `Gtk.ScrolledWindow` (today's `track_scroll`) moves out
from inside the flip-stack to sit permanently below the text row, fixed
to a height showing roughly 5-6 track rows before scrolling (up from the
98px squeeze). Always populated and visible; no toggle, no flip button.

**5. Control row** — unchanged.

## Data flow

- **Population trigger**: `_sync_back_plate` (renamed `_sync_tracklist`)
  currently only runs when the flip-card's back face is visible
  (`deck_stack.get_visible_child_name() == "back"` gate in `update()`).
  Since the tracklist is now always on screen, this gate is removed —
  it runs whenever the current artist/title changes.
- **Enrichment timing**: album/tracklist metadata arrives async
  (`metadata.run_enrich` kicks a background thread; `get_enriched_meta`
  reads whatever's cached). On a track change, populate immediately with
  whatever's cached (likely the fallback "no tracklist" view), then
  re-sync once more after the same ~3s delay `_async_fetch_cover` already
  waits for enrichment to land, rather than rebuilding the list on every
  1s daemon poll tick regardless of whether anything changed.

## CSS (`common.py`)

- `.album-deck-wrapper` and `.album-deck-wrapper.flipped` — removed
  (rotation transform is gone; there's no wrapper/stack left to rotate).
  Styling that gave the art its shape/shadow moves directly onto
  `.cover-art`.
- `.cover-art` — `min-width`/`min-height` bump from `98px` to the new
  target size.
- `.art-card-back` → renamed `.tracklist-panel` (it's a permanent panel
  now, not a flip back-face); background/border/shadow styling carries
  over unchanged.
- `.tracklist-container label` — unchanged.
- `.corner-tag` family, `.corner-tag-flip` — `.corner-tag-flip` is
  removed along with the flip button; LIVE/format/REC corner-tag classes
  are unchanged.

## Removed

- `flip_btn`, `on_flip_clicked` — deleted; no flip interaction remains.
- `deck_stack`, `stack_wrapper`, `cover_overlay`'s role as a flip-stack
  container — the art (`cover_stack`) and tracklist (`track_scroll`)
  become independent siblings in the vertical card layout instead of
  front/back pages of a `Gtk.Stack`.
- `-3deg`/`2deg rotate` transforms on the art.

## Explicitly out of scope

- Library/Discover drawer panels, `TornSeparator`/seam drag physics,
  `NavColumn`, volume slider (`ThreadSlider`), control row buttons —
  untouched, per the 2026-07-25 pass's same scoping.
- Palette/color source, fonts, fabric/craft-texture SVG filter —
  untouched; colors continue to come from `palette.load()`.
- `_search_cache` race in `radiobrowser.py` — unrelated pre-existing
  issue, tracked separately.
- Audio-reactive/decorative EQ visualizer as a *new* feature — the
  existing `EqStrip` behind the text block is kept as-is, just
  repositioned; no new visualizer work here.

## Testing

No test infrastructure exists in this repo (consistent with prior
specs). Manual verification via the working-tree dev launch flow:

1. Launch the app, play a station with enriched metadata available —
   confirm album art renders large and square at the top of the card,
   with LIVE/format/REC corner tags still positioned correctly and still
   clickable (REC toggle + right-click mode cycle).
2. Confirm title/artist/genre text renders in its own row below the art,
   with the EQ strip animating behind it while playing and inert while
   stopped.
3. Confirm the tracklist renders below the text row, always visible,
   showing ~5-6 rows before scrolling, with the current track bolded.
4. Change tracks (or switch stations) and confirm the tracklist updates:
   immediately with whatever's cached, then again once enrichment lands
   a few seconds later if it wasn't cached yet.
5. Confirm no flip button/interaction remains anywhere on the art.
6. Confirm the popup window grows taller (not wider) to fit the new
   layout, still anchored top+right, and the seam-drag drawer
   (Library/Discover) still opens/closes/animates correctly to the left
   of the now-taller Now Playing card.
7. Confirm across at least two palette themes that `.cover-art` and the
   renamed `.tracklist-panel` still read correctly (background, border,
   shadow) in both.
