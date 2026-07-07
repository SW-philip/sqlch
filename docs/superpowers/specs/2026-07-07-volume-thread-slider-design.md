# Volume Control: Zipper + Pepper → Thread & Button — Design

**Date:** 2026-07-07
**Status:** Approved

## Summary

Replace the `ZipperSlider` + `PepperToggle` pair with a single widget,
`ThreadSlider`: a tufted upholstery button riding a dashed sewing thread.
The zipper (denim/hardware) and pepper (vegetable sticker) read as two
unrelated material worlds bolted together; this collapses them into one
object with two homes — the button lives on the thread for normal 0–100%
volume, and boost is the *same* button physically dragged off the thread
and snapped onto a fixed "nub" (an empty buttonhole loop) past the
track's end. No second widget class, no unrelated iconography.

This stays in the same "chaotic pragmatic" fabric-craft world as the REC
pop-it bubble and corner tags — tactile, hand-sewn, not a clean modern
fader.

## File organization

`sqlch_gui/ui/controls.py` keeps `RecordBubble` as-is. `ZipperSlider` and
`PepperToggle` are both deleted outright (not deprecated) and replaced by
one new class, `ThreadSlider`. The single import site in
`sqlch_gui/ui/now_playing.py` updates accordingly.

## Component: `ThreadSlider`

A `Gtk.DrawingArea`, horizontal, `hexpand=True`, fixed height (~34px),
backed by a `Gtk.Adjustment` with range **0.0–1.0**, same as
`ZipperSlider` today. Internally tracks one additional piece of state
beyond the adjustment: `self.boosted: bool`.

### Rendering (`_on_draw`)

- **Thread**: a single dashed line running the full track width (the old
  zipped-tape / open-teeth distinction is gone — no two visual states
  for the track itself). Color derives from the palette (`BAR`-shaded,
  same helper `_shade()` already in this file), not hardcoded.
- **Button**: drawn at the thread position when `not self.boosted`, or
  snapped into the nub position when `self.boosted`. A domed radial
  gradient (convex bump, same highlight-upper-left trick as
  `RecordBubble`'s idle state) with a single dark center dimple and four
  short diagonal pull-lines radiating from it (the tufted/chesterfield
  look), rather than the old 4-hole sew-through pattern or the zipper
  pull tab.
  - Idle (on thread): gray/neutral, palette `BAR`-derived, matching the
    thread.
  - Boosted (in nub): recolored using the palette's `FORTE` key (the
    codebase's existing warning/alert semantic — already used for the
    REC badge and destructive-action buttons in `common.py`), not a
    hardcoded red. This is a deliberate departure from this file's prior
    "hardcoded literals, no `palette.py`" convention for the gold pull /
    pepper colors; the idle button/thread grays move to palette-derived
    values too, so the whole widget is consistently theme-driven.
- **Nub**: a small empty buttonhole loop (ellipse + short center line)
  drawn at a fixed position past the thread's right edge, at all times
  — occupied or not. It's the discoverability cue that something lives
  out there.
- **Ghost marker**: while boosted, a faint dashed ring is drawn at the
  thread position the button will return to (the pre-boost value's
  norm position), so the track still communicates "parked here."

### Interaction

- **Normal range** — identical to `ZipperSlider` today:
  - `GestureClick` (button 1, `released`): click anywhere on the thread
    jumps the button there (only when `not self.boosted`; see below for
    boosted-state click handling).
  - `GestureDrag`: relative-delta drag along x, same sensitivity
    approach as today.
  - `EventControllerScroll` (vertical axis): nudges value by a fixed
    step.
  - All three emit `value-changed(float)`, same signal shape as before.
- **Engaging boost** (only via drag, not click): during a
  `GestureDrag`, if the running position goes past the thread's right
  edge, the widget tracks it as "reaching for the nub" rather than
  clamping to 1.0. On `drag-end`:
  - If the release position is at or past the nub's snap threshold (a
    fixed distance past the track edge, roughly the nub's own width),
    the button snaps fully into the nub: `self.boosted = True`,
    `self._pre_boost_norm = <norm position before the drag began>`, and
    the widget emits `boost-toggled(True)`. The adjustment's value is
    **not** changed by this — it stays wherever it was, matching the old
    pepper's "track never represents 120%" rule.
  - If released past the edge but short of the snap threshold, the
    button springs back to the nearest valid thread position (a
    `value-changed` emit if that differs from the drag-start value,
    otherwise no-op) — no boost engaged.
  - A plain click past the track's right edge (on the nub, no drag) is a
    no-op — boost only engages through the drag gesture.
- **Disengaging boost** — both paths supported:
  - **Click on the docked (boosted) button**: `self.boosted = False`,
    restores the button to `self._pre_boost_norm`'s value (i.e. exactly
    the pre-boost adjustment value — since the adjustment was never
    changed, this is just a redraw), emits `boost-toggled(False)`. No
    `value-changed` emit since the value never moved.
  - **Drag the docked button back onto the thread**: as soon as the drag
    crosses back onto valid thread coordinates, `self.boosted = False`
    is set immediately (emits `boost-toggled(False)`), and the drag
    continues to behave like a normal thread drag from that point,
    landing wherever released and emitting `value-changed` normally.
    This mirrors "any manual interaction while boosted un-boosts first,
    then the manual value applies," but the un-boost now originates
    inside the widget rather than being orchestrated by
    `NowPlayingPanel`.
  - **Scroll while boosted**: un-boosts first (`boosted = False`,
    `boost-toggled(False)` emitted) using `_pre_boost_norm`'s value as
    the new baseline, then applies the scroll step from there and emits
    `value-changed`. Symmetrical with drag.
- Emits `value-changed(float)` and `boost-toggled(bool)` — the same two
  signal shapes `NowPlayingPanel` already listens for today (currently
  split across `ZipperSlider` and `PepperToggle`; now both live on one
  widget).

## Boost semantics (owned by `NowPlayingPanel`)

Unchanged from the current design in spirit, just triggered by one
widget's two signals instead of two widgets:

- `NowPlayingPanel` holds `self._pre_boost_vol: float | None = None`
  (kept for the `wpctl` call target, distinct from the widget's own
  internal `_pre_boost_norm` bookkeeping for redraw purposes).
- `boost-toggled(True)`: store `self.vol_adj.get_value()` into
  `_pre_boost_vol`, run `wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.20`.
- `boost-toggled(False)`: run
  `wpctl set-volume @DEFAULT_AUDIO_SINK@ {_pre_boost_vol:.2f}` (fallback
  `0.0` if `None`), clear `_pre_boost_vol`.
- `value-changed` firing while boost is in the middle of being
  disengaged by the widget (drag-back or scroll case above) applies
  normally through the existing `on_vol_changed` path — no special
  casing needed in `NowPlayingPanel`, since the widget always emits
  `boost-toggled(False)` before the corresponding `value-changed`.
- Boost is independent of playback state; `reset_ui()` does not touch
  it, unchanged from today.

## Layout (`sqlch_gui/ui/now_playing.py`)

- `hub_row` unchanged (REC bubble → Stop → Mute).
- `vol_row` now holds a single `ThreadSlider` (`hexpand=True`) — the
  separate pepper widget entry is removed. The row's width no longer
  needs to reserve space for two widgets side by side; the nub is drawn
  inside `ThreadSlider`'s own allocation, past the thread.
- Caption row below (`VOL` tag, `.knob-tag` class) unchanged.
- `update_indicators`'s `handler_block`/`vol_adj.set_value`/
  `handler_unblock` dance carries over unchanged, retargeted at
  `self.vol_slider` (now a `ThreadSlider`).
- `self.pepper` and its construction/connection lines are deleted.
  `self._pre_boost_vol` stays on `NowPlayingPanel`, now fed by
  `ThreadSlider`'s `boost-toggled` signal instead of `PepperToggle`'s.

## Unchanged

- `RecordBubble`, its signals, mode cycling, corner badge.
- Daemon/CLI plumbing, polling cadence, mute button and its icon states.
- `wpctl` as the volume-setting mechanism (both manual and boosted
  paths).
- Adjustment range (0.0–1.0) and `on_vol_changed`'s `wpctl` call.
- `lbl_vol_percent`'s behavior: it never reflects the boosted 120%
  value, same as today.

## Files touched

- `sqlch_gui/ui/controls.py`: delete `ZipperSlider` and `PepperToggle`,
  add `ThreadSlider`, keep `RecordBubble` as-is.
- `sqlch_gui/ui/now_playing.py`: update import, replace `vol_slider`/
  `pepper` wiring with the single `ThreadSlider`, keep `_pre_boost_vol`
  bookkeeping but feed it from the new widget's signals.

No daemon/protocol changes. No new CSS beyond the existing `.knob-tag`.

## Testing

No test infrastructure in this repo. Manual verification:

1. Run the app; confirm the thread renders as a plain dashed line with
   the tufted button parked at the current volume position, and an
   empty nub visible past the track's end.
2. Drag the button, click elsewhere on the thread, and scroll over it —
   confirm all three change volume and redraw correctly.
3. Drag the button past the track's right edge and release on/past the
   nub: confirm it snaps in, recolors to the `FORTE` palette color, and
   volume jumps to 120%. Confirm a drag that goes past the edge but
   stops short of the nub springs back without engaging boost.
4. While boosted, click the docked button: confirm it pops back to the
   exact pre-boost volume and position.
5. While boosted, drag the button back onto the thread: confirm boost
   disengages and the dropped position becomes the new volume.
6. While boosted, scroll over the widget: confirm boost disengages and
   the scroll nudge applies from the pre-boost value.
7. Switch palettes (edit `palette.sh` or point `SQLCH_GUI_PALETTE`
   elsewhere) and confirm the thread/button idle colors and the boosted
   `FORTE` color both update live, without restarting the app (the GUI
   file-watches `palette.sh`).
8. Confirm REC bubble, Stop, and Mute are visually/behaviorally
   unaffected.
