# Now Playing: Flanking Nav/Controls + Collapsible Library/Discover — Design

**Date:** 2026-07-09
**Status:** Approved

## Summary

Two related changes to `sqlch_gui`:

1. **Now Playing's layout.** The album art currently sits in a horizontal row
   with only a flip-to-tracklist button beside it (`now_playing.py`'s
   `deck_box`), while REC/STOP/MUTE live in a separate "control deck" card
   below. Collapse that dead space: the existing nav column (today a
   window-global sidebar) moves to sit directly left of the album art, and
   REC/STOP/MUTE move to sit directly right of it. The album art itself grows
   to match the height of the REC/STOP/MUTE button stack, so there's no
   leftover gap on either side. The separate control-deck card is removed —
   only the volume slider, play/pause, and tech readout remain below.

2. **Nav model.** Today, `window.py` uses a `Gtk.Stack` to swap the *entire*
   window content between three full-page panels (Now Playing / Station List
   / Discover), with a sidebar of icon buttons living outside the stack. That
   sidebar becomes the nav column described above, and the swapping model
   changes: **Now Playing is always visible** (it's the permanent top
   section, never replaced), and Station List / Discover become collapsible
   dropdown panels that appear *underneath* it.

## Why

The current layout has the album art awkwardly alone in its row (just a flip
button for company) while related controls sit in a separate card below,
and a full-height global sidebar that's mostly empty space next to a small
window. Flanking the art with the nav column and REC/STOP/MUTE — and letting
the art grow to fill the height that creates — turns dead space into a
tighter, more purposeful hub. Making Now Playing permanently visible (instead
of one of three swappable pages) also matches how the app is actually used:
it's a radio player first, and station browsing/discovery are secondary,
occasional actions that shouldn't require losing sight of what's currently
playing.

## Layout

### The permanent Now Playing block

Top row, horizontal, three flanks:

- **Left — nav column** (was the window-global `sidebar` in `window.py`):
  three icon buttons, same top-to-bottom order as today:
  - **Mini** (renamed from "Now Playing"): a custom-drawn spool glyph — two
    dashed ellipse rims joined by two verticals, echoing the thread/button
    visual language already established by `ThreadSlider` and `RecordBubble`
    (drawn via `Gtk.DrawingArea`/Cairo, not a symbolic icon name, matching
    `controls.py`'s existing hand-drawn style). Clicking it collapses
    whichever dropdown is open (see Nav behavior below).
  - **Library** (`view-list-symbolic`, unchanged) — opens the Station List
    dropdown.
  - **Discover** (`folder-saved-search-symbolic`, unchanged) — opens the
    Discover dropdown.
- **Center — album art** (`cover_stack`/`deck_stack`, unchanged internals):
  grows from its current 120px image / 124px min-size to whatever height the
  REC/STOP/MUTE stack occupies (today: 52px bubble + 44px + 44px + spacing —
  final numbers tuned during implementation so the two visually line up with
  no gap). The flip-to-tracklist button is removed as a standalone button;
  its click target becomes a small overlay glyph in the album art's own
  bottom-right corner (`cover_overlay` already hosts `LIVE`/format corner
  tags top-left/top-right via `Gtk.Overlay` — this is a third corner tag in
  the same spot-family, bottom-right, using the existing
  `object-flip-horizontal-symbolic` icon).
- **Right — transport buttons**: `RecordBubble` (with its mode badge overlay,
  unchanged), then `Stop`, then `Mute`, stacked vertically in that order.

Below this row, unchanged in content and order: title/artist/genre text
block, `EqStrip`, volume slider (`ThreadSlider`, full width), play/pause
(`btn_toggle`, centered "primary" control button), tech readout strip
(bitrate/channels/BT/device/REC timer badges). The separate "control deck"
`Gtk.Box` card that currently hosts the hub row + volume + play/pause is
removed as a distinct card — its remaining contents (volume, play/pause,
readout) live directly in `NowPlayingPanel`'s main vertical layout, since
REC/STOP/MUTE no longer need their own row.

### Nav behavior

Mini/Library/Discover are **not** independent toggle buttons — they behave
like a single mutually-exclusive selector, but with an asymmetry:

- Clicking **Library** opens the Station List dropdown, auto-collapsing
  Discover if it was open.
- Clicking **Discover** opens the Discover dropdown, auto-collapsing Library
  if it was open.
- Clicking **Library** or **Discover** again while it's *already* the open
  one is a no-op — it does not close.
- Clicking **Mini** is the only way to collapse an open dropdown back down to
  showing just the Now Playing block.
- Only one dropdown can be open at a time.
- The dropdown region has a **fixed max-height and scrolls internally**
  (both `StationListPanel` and `DiscoverPanel` already wrap their content in
  their own internal `Gtk.ScrolledWindow`, so this is just a height cap on
  an already-scrollable widget, not a new nested-scroll problem). The window
  itself **never resizes** when a dropdown opens or closes.
- The active nav icon gets the existing `.nav-btn.active` CSS treatment
  (today's highlight style); Mini is visually "active" whenever no dropdown
  is open.

## Component structure

- `window.py`'s `main_box` stops being `[sidebar][Gtk.Stack of 3 pages]`.
  Instead it becomes a single vertical arrangement: `NowPlayingPanel` (which
  now owns/embeds the nav column as part of its own flanking row) directly
  above a dropdown container that shows either `StationListPanel`,
  `DiscoverPanel`, or nothing (height-collapsed), controlled by whichever
  nav icon was last clicked.
- `NowPlayingPanel` needs a way to tell `window.py` "Library was clicked" /
  "Discover was clicked" / "Mini was clicked" without owning
  `StationListPanel`/`DiscoverPanel` itself (those remain instantiated and
  owned by `window.py`, as today). This is a signal (e.g.
  `nav-selected` with a string payload) that `SqlchPopupWindow` connects to,
  same ownership direction as today's `flip_btn`/`record-toggled` pattern
  already used inside `now_playing.py`.
- `SqlchPopupWindow.switch_panel` is replaced by logic that shows/hides the
  dropdown container's child and toggles nav button `.active` classes,
  rather than calling `Gtk.Stack.set_visible_child_name`. `station_list.py`'s
  existing `on_shown()` refresh hook still fires when Library's dropdown
  opens (same trigger point, different call site).
- The nav column's three buttons and their mutual-exclusion click logic are
  a natural candidate for a small dedicated class (e.g. `NavColumn` in
  `controls.py` or a new small module) rather than being built inline in
  `NowPlayingPanel.__init__`, since `NowPlayingPanel` is already a large
  file — final decision on exactly where this lives is left to the
  implementation plan.

## Explicitly out of scope

- Any change to `StationListPanel` or `DiscoverPanel`'s internal content,
  filtering, or CRUD behavior — they're relocated, not redesigned.
- Redesigning Library/Discover's icons — only Mini gets the new spool glyph.
- Persisting which dropdown was last open across app restarts.
- Keyboard navigation/shortcuts for the nav column (mouse/touch only, same
  as today's sidebar).

## Testing

No test infrastructure exists in this repo (consistent with prior specs).
Manual verification via the working-tree dev launch flow:

1. Launch the app — Now Playing block is the only thing visible, Mini shows
   as active, no dropdown present, window at its normal compact size.
2. Click Library — Station List appears below, scrollable, capped height,
   window doesn't resize; Mini no longer shows active.
3. Click Library again — no change (still open, not closed).
4. Click Discover — Discover replaces Station List below (Library's dropdown
   closes); still one dropdown, still capped height.
5. Click Mini — dropdown collapses, back to Now Playing only.
6. While a dropdown is open, confirm Now Playing block above it keeps
   updating live (track changes, volume, REC state) exactly as it does
   today — it's the same widget instance, not torn down.
7. Visually confirm album art height now matches the REC/STOP/MUTE stack
   with no gap, and the flip-to-tracklist corner glyph still flips to the
   tracklist back-plate and back.
