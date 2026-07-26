# Now Playing Card Redesign — Merged Deck

**Date:** 2026-07-25
**Status:** Approved

## Summary

Restructure `NowPlayingPanel` from a flanked, multi-patch layout (separate
nav sidebar, cover art, transport column, EQ strip, text block, volume row,
readout chip strip) into a single merged "deck" patch: one card, three
rows (nav, art+text, controls), one plain-text readout line instead of six
bordered chips. Only the outer popup window keeps the thick stitched
dashed-border frame — every element inside the card loses its own
individual hem/border. `RecordBubble` is retired in favor of a fourth
corner tag on the cover art; `NavColumn` flattens from a vertical icon
rail into a horizontal row; `ThreadSlider`'s drag-past-the-end boost nub
is replaced by plain drag (0-100%) plus scroll-to-boost.

## Why

The current card was flagged as "too busy, clunky, and messy" — mostly
decorative noise (a dashed hem on nearly every widget class) and
fragmented layout structure (nav column, art, transport column, EQ strip,
text, volume, play, readout are all separate visually-bordered zones).
Three wireframe directions (Merged Deck / Two-Zone Split / Minimal Chrome)
were reviewed via the visual companion; Merged Deck was chosen because it
keeps the fabric aesthetic (per the system-wide Paper Mario patch
convention) while cutting from ~6 competing dashed borders down to 1.
Library/Discover panels are intentionally out of scope for this pass —
they get their own pass later once this pattern is proven.

## Layout

Three rows inside a single `.card` patch, top to bottom:

**1. Nav row** — `NavColumn`, flattened to `Gtk.Orientation.HORIZONTAL`,
left-aligned; a plain-text readout label, right-aligned, replacing the six
bordered `.tech-badge` chips with one string like `28% · 128k · Stereo ·
BT · Built-in Audio` (segments omitted when their data is absent, same
`set_visible` logic as today just feeding into one label instead of six).

**2. Art + text row** — cover art inline on the left (`cover_overlay`,
unchanged internals: front/back deck stack, flip corner tag), title/
artist/genre text to its right instead of centered below. The `EqStrip`
renders behind the text block rather than as its own row: a
`Gtk.Overlay` with `EqStrip` as the main child (sized to the text block's
footprint) and the title/artist/genre `Box` as the overlay on top —
same overlay-vs-main-child pattern already used for the corner tags
(overlay children paint over the main child; the label box needs to
report its own size for the overlay to size correctly, matching the
existing corner-tag overlay pre-measure approach).

**3. Control row** — Stop · Volume · Mute · Play, one horizontal row.
Play (`control-btn primary`) stays visually elevated — larger, filled,
dark — as the sole emphasized element in the row; Stop and Mute stay
small icon buttons. The volume fader expands to fill the space between
Stop and Mute.

## Corner tags (cover art)

Four tags total, unchanged positions for the existing three:
- LIVE — top-left (unchanged)
- format — top-right (unchanged)
- flip-to-tracklist — bottom-right (unchanged)
- **REC — bottom-left (new)** — plain text tag from the same
  `.corner-tag` family as LIVE/format (not a Cairo-drawn silicone
  bubble). Shows `REC·F` or `REC·T` (mode letter always visible, no
  right-click-to-reveal needed). Red (`FORTE`) background when
  recording, muted/neutral when idle. Click toggles recording; right-click
  cycles FULL/TRACK mode — same interaction `RecordBubble` had, just on a
  `Gtk.Button` with a secondary `GestureClick` (button 3) added for the
  mode-cycle, instead of a `Gtk.DrawingArea`. The elapsed-recording timer
  (`REC 00:34`, currently a `tech-badge.rec-badge` chip) moves to the
  tag's tooltip rather than staying in the readout line — the readout
  line is meant to shrink to steady-state device/quality info, not a
  ticking clock.

## Volume slider

`ThreadSlider` drops the drag-past-the-end nub mechanic entirely:

- **Drag/click**: plain proportional fader across the full track width,
  0-100%, no separate nub zone to navigate around.
- **Boost (>100%, up to 120%)**: scroll-wheel only, while hovering the
  slider. Scrolling up past a value already at 100% keeps pushing the
  fill into a fixed small overflow zone past the track's right edge (up
  to the 120% cap); the fill/button color shifts to `FORTE` once past
  100% as the boosted-state cue. Scrolling down un-boosts smoothly back
  through 100%. `boost-toggled` still fires (on crossing the 100%
  threshold each direction) so `NowPlayingPanel.on_boost_toggled` keeps
  driving the real `wpctl` volume unchanged.
- Exact pixel geometry (overflow-zone width, dot spacing, button radius)
  is a Cairo draw — tune live against the running dev instance rather
  than derive analytically, consistent with how prior control-widget
  specs in this repo have handled it.

## Nav row

`NavColumn` changes `orientation` from `VERTICAL` to `HORIZONTAL` and
drops its `.sidebar` CSS class (the separately-colored background patch)
— it becomes a plain row of icon buttons sitting directly on the card's
background, consistent with "only the outer window keeps a stitched
frame." Mini/Library/Discover selection logic, the hand-drawn spool glyph
for Mini, and `set_active()` (used by seam-drag-driven drawer state)
are unchanged — this is a layout/CSS change only.

## CSS (`common.py`)

- `.sidebar` — remove (superseded by the flattened nav row using
  transparent/no background).
- `.cover-art`, `.control-btn`, `.control-btn.primary` — drop the
  `hem(...)` box-shadow layer and the `border: 2px dashed {thread}`;
  keep `border-radius`, background color, and the plain drop-shadow
  (`slight`/`slight_lift`/`slight_press`) for depth without the stitched
  edge.
- `.tech-badge` — becomes dead code from `now_playing.py`'s perspective
  (readout is now one plain label, no `add_css_class("tech-badge")`
  calls); leave the CSS rule in place since `.tag-chip` shares the
  selector and `.tag-chip`/`.small-badge` are still used by
  `discover.py` (out of scope for this pass).
- `.corner-tag` family — unchanged (REC reuses it as-is).
- `.card` keeps its own hem/border — it's the single remaining inner
  patch.
- `.popup-window` — unchanged; it's the one border that stays.

## Removed

- `RecordBubble` class in `controls.py` — deleted. Its Cairo
  silicone-bubble rendering, `MODES` cycling, and `record-toggled`/
  `mode-changed` signals are superseded by the REC corner tag's plain
  button + gesture controllers described above.
- `rec_bubble_overlay`, `rec_wrap`, `lbl_rec_mode`, `lbl_rec_tag`,
  `right_col` in `now_playing.py` — removed; REC lives on the cover art
  overlay now, Stop/Mute move into the merged control row.
- `deck_box`'s flanking structure (`nav_column` | `cover_overlay` |
  `right_col`) — removed in favor of the three-row layout above.
- Six individual `tech-badge` labels (`lbl_vol_percent`, `lbl_rec`,
  `lbl_bitrate`, `lbl_channels`, `lbl_bt`, `lbl_device`) — collapsed into
  one plain-text readout label (recording elapsed time excluded, per
  above — it moves to the REC tag's tooltip).

## Explicitly out of scope

- Library/Discover drawer panels (`station_list.py`, `discover.py`,
  `.list-plate`/`.station-row`/`.list-header` CSS) — untouched.
- `TornSeparator` (drawer drag handle) and drawer spring-physics
  animation in `window.py` — untouched.
- Palette/color source, fonts, or the fabric/craft-texture SVG filter —
  untouched; every color continues to come from `palette.load()`.
- Cover art flip-to-tracklist mechanic, back-plate rendering — untouched.
- Any change to daemon polling, `update_indicators()`'s data inputs, or
  the `wpctl`/subprocess calls themselves — this is a layout/CSS/widget
  pass, not a functional one (aside from the slider's own interaction
  mechanic, which is explicitly in scope).

## Testing

No test infrastructure exists in this repo (consistent with prior specs).
Manual verification via the working-tree dev launch flow:

1. Launch the app — Now Playing card renders as one visually merged
   patch: nav row on top, art+text row, control row, no competing dashed
   borders inside the card (only the outer window frame and the card's
   own border remain).
2. Confirm nav row is horizontal, has no separate colored background
   patch, and Mini/Library/Discover selection + drawer sync (`set_active`
   from seam drags) still work.
3. Confirm the readout line shows/hides segments correctly as
   bitrate/channels/BT/device become available or unavailable (compare
   against today's chip visibility logic).
4. Confirm EQ strip animates behind the title/artist text when playing,
   is inert/invisible when stopped, and doesn't visually collide with
   the text.
5. Confirm REC corner tag: click toggles recording, right-click cycles
   FULL/TRACK (mode letter updates immediately), tag turns red while
   recording, hover tooltip shows elapsed time while recording.
6. Confirm volume slider: click/drag sets 0-100% with no dead zone or
   nub to navigate; scrolling up past 100% while hovering boosts to
   120% with a visible color shift, scrolling back down un-boosts;
   actual `wpctl` volume changes match the displayed state at each step.
7. Confirm Play stays visually larger/emphasized in the control row
   while Stop/Mute are smaller flanking buttons, and all three remain
   comfortably clickable at current sizing.
8. Confirm across at least two different palette themes (switch
   `palette.sh` themes) that the simplified `.cover-art`/`.control-btn`
   styling (drop-shadow only, no dashed border) still reads correctly in
   both light and dark palettes.
9. Confirm Library and Discover panels are visually unchanged (this pass
   didn't touch their CSS classes or structure).
