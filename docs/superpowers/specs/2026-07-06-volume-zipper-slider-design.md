# Volume Control: Rotary Knob → Zipper Slider — Design

**Date:** 2026-07-06
**Status:** Approved

## Summary

Replace the volume `RotaryKnob` with a full-width horizontal "zipper"
slider: a track that visually unzips as volume drops and zips shut as it
rises, with a pull tab you drag, click-to-jump, or scroll. This is
"chaotic pragmatic" rather than a clean modern fader — a jury-rigged
control in the same fabric/paper-craft world as the REC pop-it bubble and
corner tags, not a smooth OS-standard widget.

Alongside it, a new discrete boost control: a hot-pepper sticker glued
just past the track's end that toggles volume to a hard-coded 120%
("LOUD"). The continuous >100% boost range the knob used to offer
(0.0–1.3) goes away — the track now only covers 0–100%, and 120% is a
single fixed step reached only through the pepper.

## File organization

`sqlch_gui/ui/knob.py` is renamed to `sqlch_gui/ui/controls.py`. Once
`RotaryKnob` is gone, nothing in the file is a knob — `RecordBubble` is a
press-toggle, and the two new widgets are a slider and a sticker. The one
import site in `sqlch_gui/ui/now_playing.py` updates accordingly.

`RotaryKnob` is deleted outright, not deprecated or kept for reference —
it is only ever used for volume (confirmed by grep across `sqlch_gui/`),
and its replacement is a full rewrite, not an extension. This mirrors how
`RecordKnob` became `RecordBubble` in the previous dial→bubble rewrite:
same file, same "the old shape's metaphor no longer applies" reasoning.

## Component: `ZipperSlider`

A `Gtk.DrawingArea`, horizontal, `hexpand=True`, fixed height (~34px),
backed by a `Gtk.Adjustment` with range **0.0–1.0** (replacing the old
0.0–1.3 — see "Range change" below).

**Rendering** (`_on_draw`), all literal cairo shapes/gradients matching
the existing hardcoded-color convention in this file (no `palette.py`
involvement, same as `RotaryKnob`/`RecordBubble` today):

- From the left edge to the pull's x position: a closed zip tape (solid
  fill) with a herringbone mesh-teeth pattern drawn down its center.
- From the pull's x position to the right edge: an "open" gap — teeth
  splayed apart (drawn as short diagonal dashed strokes angling away from
  each other), tape not filled.
- The pull itself: a tilted gold zipper-pull tab (small rounded body +
  angled tab, matching the shape used in the brainstorm mockup) straddling
  the zipped/open boundary.
- Norm position: `(value - lower) / (upper - lower)`, same formula
  `RotaryKnob` used for its angle, just mapped to an x-coordinate along
  the width instead of an angle.

**Interaction:**

- `GestureClick` (button 1, `released`): compute the click's x fraction of
  the widget's width, clamp to `[lower, upper]`, `set_value()` — click
  anywhere on the track jumps the pull straight there. This is new;
  `RotaryKnob` had no click-to-jump.
- `GestureDrag`: same relative-delta approach `RotaryKnob` used, but reads
  `offset_x` instead of `offset_y` (horizontal drag now, not vertical).
  Sensitivity constant carries over unchanged in spirit (tuned to the new
  axis/track length).
- `EventControllerScroll` (vertical scroll axis, same as today): nudges
  value by a fixed step, unchanged from `RotaryKnob`'s scroll handling.
- Emits `value-changed(float)`, identical signal shape to `RotaryKnob`, so
  `NowPlayingPanel.on_vol_changed` requires no signature changes.

## Component: `PepperToggle`

A small (~34px) `Gtk.DrawingArea`, drawn as a simplified pepper silhouette
(rounded body + small stem) — not photorealistic, scoped to what reads
clearly at 34px. Reuses `RecordBubble`'s convex-bump-idle /
pressed-dimple-active gradient trick for its two states: green idle,
hotter/redder gradient when boosted. Sits immediately after the track, as
if glued past its end.

- Single `GestureClick` (button 1) toggles internal `active` bool, calls
  `queue_draw()`, emits a new `boost-toggled(bool)` signal.
- Exposes `set_active(active: bool)`: sets the internal bool, redraws, and
  emits nothing (mirrors `RecordBubble.set_state()`'s pattern of an
  external, signal-free push). `NowPlayingPanel` calls this to force the
  pepper back to idle when a manual slider interaction overrides boost
  (see below) — the only external write path into the widget's state.
- No `set_state()`/daemon-truth reflection like `RecordBubble` has — see
  below.

## Boost semantics (owned by `NowPlayingPanel`)

Unlike `RecordBubble`, `PepperToggle` does not reflect polled daemon
truth — it's a simple local optimistic toggle, matching the "toggle"
behavior (press again to restore) rather than "reflect current system
state." This is a deliberate simplification: if the `wpctl` call silently
failed, the pepper could locally claim "boosted" while real volume didn't
change. Accepted trade-off for a single-user local desktop volume
control — not worth adding state-reconciliation machinery for.

- `NowPlayingPanel` holds `self._pre_boost_vol: float | None = None`.
- `boost-toggled(True)`: store `self.vol_adj.get_value()` into
  `_pre_boost_vol`, run `wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.20`. The
  slider/adjustment itself is **not** changed — it stays wherever it was,
  visually pinned at its own range (which tops out at 100%). The track
  never represents the 120% state; only the pepper's own visual flip does.
- `boost-toggled(False)` (pepper pressed again while boosted): run
  `wpctl set-volume @DEFAULT_AUDIO_SINK@ {_pre_boost_vol:.2f}` (falling
  back to `0.0` if somehow `None`), clear `_pre_boost_vol`.
- Any manual `ZipperSlider` interaction (`value-changed` firing from
  drag, click-to-jump, or scroll) while boosted: first call
  `pepper.set_active(False)` and clear `_pre_boost_vol`, *then* apply the
  manual value via the existing `on_vol_changed` path. Touching the fader
  always means manual control wins — no silent fight between "boosted"
  and "the slider says X."
- Boost is independent of playback state; `reset_ui()` does not touch it
  (mirrors how volume/mute already work today — they're not
  playback-scoped).

## Layout (`sqlch_gui/ui/now_playing.py`)

- `hub_row` keeps REC bubble → Stop → Mute (in that order); the old
  `vol_wrap` (knob + "VOL" tag) is removed from it.
- A new full-width row is added directly below `hub_row`, inside `deck`:
  `ZipperSlider` (`hexpand=True`) followed immediately by `PepperToggle`
  (fixed size, no expand), spaced the same as other control gaps (12px).
- Beneath that row, a caption row holds just a "VOL" label reusing the
  existing `.knob-tag` CSS class — no percent readout duplicated here.
  `self.lbl_vol_percent` in the existing tech-badge strip remains the
  single source of truth for the numeric percentage; nothing about it
  changes.
- `update_indicators`'s existing `handler_block` / `vol_adj.set_value` /
  `handler_unblock` dance around the daemon-polled `vol` carries over
  unchanged, just retargeted at `self.vol_slider` instead of
  `self.vol_knob`.

## Range change

`self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, ...)` —
`upper` changes from `1.3` to `1.0`. `on_vol_changed` keeps calling
`wpctl set-volume @DEFAULT_AUDIO_SINK@ {val:.2f}` unchanged; the boost
path is the only place `1.20` appears, as a literal.

## Unchanged

- `RecordBubble`, its signals, mode cycling, corner badge — untouched.
- Daemon/CLI plumbing, polling cadence, mute button and its icon states.
- `wpctl` as the volume-setting mechanism (both manual and boosted paths).

## Files touched

- `sqlch_gui/ui/knob.py` → renamed `sqlch_gui/ui/controls.py`: delete
  `RotaryKnob`, add `ZipperSlider` and `PepperToggle`, keep `RecordBubble`
  as-is.
- `sqlch_gui/ui/now_playing.py`: update import, replace `vol_wrap`/
  `RotaryKnob` wiring with the new row layout, add boost-toggle handler
  and `_pre_boost_vol` state.

No daemon/protocol changes. No new CSS beyond reusing `.knob-tag`.

## Testing

No test infrastructure in this repo. Manual verification:

1. Run the app; confirm the zipper track renders zipped-to-current-volume
   with an open gap past the pull, at rest.
2. Drag the pull, click elsewhere on the track, and scroll over it —
   confirm all three change volume and the track re-renders correctly at
   each.
3. Tap the pepper: volume jumps to 120%, pepper visual flips to "hot."
   Tap again: volume restores to the pre-boost value, pepper flips back.
4. While boosted, drag/click/scroll the zipper: confirm the pepper
   un-toggles and the manual value takes effect (no fight between the
   two).
5. Confirm REC bubble, Stop, and Mute are visually/behaviorally
   unaffected.
