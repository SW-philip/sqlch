# REC Control: Dial → Pop-it Bubble — Design

**Date:** 2026-07-05
**Status:** Approved

## Summary

Replace the record control's rotary-dial visuals with a "pop-it" fidget-toy
bubble, sewn into the fabric deck like the rest of the LBP-styled UI. The
dial metaphor was misleading: `RecordKnob` shares `RotaryKnob`'s bezel,
dashed stitch ring, and angle-pointer, but has no drag gesture at all —
you can't turn it. Left-click toggles recording, right-click cycles the
FULL/TRACK mode; the pointer angle was just displaying a value you set via
clicks, never by rotating. The new bubble shape makes "press me" the only
affordance on offer, and the interaction it stops implying (rotate)
disappears with it.

No behavior changes: same signal, same modes, same click bindings, same
polling-driven `set_state()`. This is a visual-only fix.

## Component: `RecordBubble` (renamed from `RecordKnob`)

`sqlch_gui/ui/knob.py` — the class name changes because the shape no
longer says "dial." Everything else on the class is untouched:
`record-toggled` signal, `MODES = ("full", "track")`, `set_state()`,
tooltip text, the left/right `GestureClick` handlers (still no drag
gesture — it was never draggable and still isn't).

`_on_draw` is rewritten:

- Drop the pointer line and the two detent dots — mode is no longer shown
  by angle.
- **Idle:** convex silicone bump — radial gradient (light highlight upper-
  left, darker toward the edge) plus a drop shadow, reads as "sticking up,
  press me." Dashed stitch ring (same convention as `RotaryKnob`'s bezel)
  in neutral grey.
- **Recording:** concave pressed dimple — inset shadow (dark upper-left,
  faint highlight lower-right) with a red gradient, plus a soft red glow.
  Dashed ring turns red. This single shape-and-color flip replaces both
  the old separate "hot ring while recording" stroke and the center-cap
  lamp — one visual change now carries the state that took two before.
- Circle stays 52px (unchanged size, keeps it visually smaller than the
  65px `RotaryKnob`).

## Mode badge (FULL / TRACK)

The badge sits outside the 52px circle (bottom-right corner overflow), so
it can't be drawn inside the `DrawingArea`'s own Cairo surface — it needs
a `Gtk.Overlay` in `sqlch_gui/ui/now_playing.py`:

- The `RecordBubble` `DrawingArea` is the overlay's main child.
- A `Gtk.Label` (text `FULL` or `TRK`) is added via `add_overlay()`,
  anchored bottom-right, with `set_can_target(False)` so it never
  intercepts the bubble's left/right clicks. This is the same
  canvas-as-main-child / label-as-overlay pattern already used for the
  `sqlch` brand tag on the deck card.
- Styling reuses the existing `.small-badge` CSS class in `common.py`
  (monospace, pill, muted background) — no new CSS. The label's text
  updates alongside `set_state()`'s existing mode-change handling.
- `rec_wrap`'s "REC" label underneath the bubble is unchanged — the badge
  is additive, not a replacement for that existing tag.

## Unchanged

- `hub_row` ordering: record | stop | volume | mute.
- `RotaryKnob` (the VOL dial) — untouched; it's the one control that
  actually earns the dial metaphor (real drag/scroll → continuous value).
- Daemon/CLI recording logic, polling, tooltip text, signal wiring.

## Files touched

- `sqlch_gui/ui/knob.py` — rename class, rewrite `_on_draw`.
- `sqlch_gui/ui/now_playing.py` — wrap the bubble in a `Gtk.Overlay` with
  the mode badge; update the `RecordKnob` import/instantiation to
  `RecordBubble`.

No CSS changes (reuses `.small-badge`), no daemon/protocol changes.

## Testing

No test infrastructure in this repo. Manual verification:

1. Run the app, confirm the bubble renders convex/idle at rest.
2. Left-click → bubble goes concave + red, corner badge still shows the
   correct mode, "REC" tag/tooltip behavior unchanged.
3. Right-click while idle → badge flips FULL/TRK; right-click while
   recording → no-op (mode locked mid-take, existing behavior).
4. Confirm VOL knob and STOP/MUTE buttons are visually unaffected.
