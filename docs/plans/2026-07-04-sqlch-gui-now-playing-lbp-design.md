# sqlch-gui Now Playing — LBP Fabric Enhancements

**Date:** 2026-07-04
**Status:** Approved for implementation

---

## Goal

Fill out the Now Playing panel's remaining empty real estate (dead space around the metadata block and control deck) with content, in the spirit of ideas originally pitched in a literal hardware/skeuomorphic register (glass LCD, metal VU meter, chrome bezels, debossed nameplate). Those ideas are re-skinned here into sqlch-gui's established "quilted fabric patch" LittleBigPlanet aesthetic — no metal, no glass, no chrome. Six additions were mocked up and visually approved against the actual now-playing/control-deck layout and current palette.

This spec covers the Now Playing panel only. The equivalent treatment for the Station Library and Discover panels (ribbon-banner section headers, lit active-row outline, mini EQ beads, pennant-shaped tags) is a separate follow-up spec.

Out of scope: audio-reactive levels (the EQ strip below is explicitly decorative, continuing the "future work" decision from the 2026-07-01 spec), window resizing, favorites/pinning.

---

## 1. Thread-brightness metadata caption

`self.lbl_genre` in `now_playing.py` currently toggles `set_visible()` — present when a genre string exists, gone otherwise. Change it to stay permanently present as a small caption, switching between a dim "unlit" state and a lit gold state:

- New CSS classes in `common.py`: `.thread-label` (dim, ~28% alpha of `SCORE`) and `.thread-label.lit` (full `ROOT`/accent color).
- `now_playing.py`: replace the `set_visible(bool(genre))` toggle in `update()` with an `add_css_class("lit")` / `remove_css_class("lit")` toggle, keeping the label always shown (with placeholder text, e.g. "GENRE", when empty).
- No new data plumbing — reuses the existing `metadata.get_icy_genre()` value already fetched.

---

## 2. Decorative EQ bead strip

A small row of soft fabric "beads" bobbing like cloth trim, sitting below the cover art. Purely decorative — this is the non-audio-reactive fallback that the 2026-07-01 spec explicitly tabled as future work, now given its LBP skin.

- New widget, same idiom as `RotaryKnob`/`RecordKnob` in `knob.py`: a `Gtk.DrawingArea` subclass (e.g. `EqStrip`) that draws N rounded bars with a Cairo `_on_draw`.
- Animation is procedural, not CSS: a `GLib.timeout_add(80, ...)` advances a phase counter and calls `queue_draw()`; each bead's height follows a phase-shifted sine wave. GTK CSS animation support is too limited for a per-bar bounce, so this follows the existing Cairo-widget pattern rather than CSS `@keyframes`.
- Colors pull from the palette (`ROOT`/`SEVENTH` gradient), no hardcoded hex.
- Only animates while a stream is actually playing; sits flat/still in the reset/not-playing state (mirrors how `reset_ui()` already zeroes out other indicators).

---

## 3. Corner tags (LIVE / format badge)

Two small crooked label pills overlaid on the top corners of the cover-art patch.

- `deck_box`'s cover-art container (`self.stack_wrapper`) gets wrapped in a `Gtk.Overlay`; the two tag labels are added as overlay children positioned top-left / top-right via CSS margins, matching the mockup's rotated-pennant look (`transform: rotate()` equivalents via GTK CSS, or fixed slight-angle via Cairo if GTK CSS transform support proves insufficient — verify during implementation).
- **LIVE tag:** visible when `update()` takes the live-stream branch (no artist/title metadata) — reuses the existing branch condition in `now_playing.py`'s `update()`.
- **Format tag (e.g. "MP3"):** new `_mpv_get_property("audio-codec-name")` fetch in `daemon.py`, following the exact pattern of the existing `audio-bitrate` / `audio-params/channel-count` fetches (`daemon.py:82`, `:94`). Wired into `update_indicators()` alongside bitrate/channels. Hidden when unavailable.

---

## 4. Knob tick-stitching + fabric tags

Applies to both `RotaryKnob` and `RecordKnob` in `knob.py`.

- Add a dashed ring around the outer bezel in each widget's `_on_draw`, via Cairo `cr.set_dash([...])` on an arc at `radius + ~4px`, using the same thread-color convention as `common.py`'s hem stitching.
- Add a small external `Gtk.Label` underneath each knob in `now_playing.py`'s `hub_row` construction, using the existing `tech-badge`-style pill CSS, reading "VOL" under `vol_knob` and "REC" under `rec_knob`.

---

## 5. Output device badge

Adds a badge to the existing `tech_box` readout strip showing the current default audio output's friendly name (e.g. "Speakers").

- New `get_sink_name()` helper in `daemon.py`: runs `wpctl inspect @DEFAULT_AUDIO_SINK@`, parses the `node.description` property. This is genuinely new plumbing (no existing code queries sink metadata beyond volume/mute) — the one item in this spec with real new surface area, though still self-contained to one helper function.
- Polled on the same cadence as the existing `wpctl get-volume` call (`daemon.py:34`) inside the volume-poll loop in `window.py`.
- Rendered as one more `tech-badge`-style label in `tech_box`, next to the existing bitrate/channels/BT badges. Hidden if the lookup fails (device unplugged, `wpctl` error) rather than showing stale/blank text.

---

## 6. Woven brand tag

A small static "sqlch" label tucked into a corner of the control-deck card (`deck` box in `now_playing.py`).

- New `Gtk.Label(label="sqlch")` with a new `.brand-tag` CSS class: dark background, dashed border (`border-style: dashed`), small monospace-styled text at low opacity, slight rotation.
- **Simplification from the mockup:** the mockup's stitch-loop nub (a small vertical line poking above the tag, done via CSS `::before`) doesn't translate — GTK's CSS engine has no pseudo-elements. Dropped; the dashed border alone carries the "sewn-in tag" read.

---

## Testing

No automated test coverage for the GTK4 widget tree (consistent with the 2026-07-01 spec). Verification is manual: run the dev instance, confirm each of the six additions against this spec and the approved mockups, and exercise the EQ strip / device badge / format tag against a real playing stream to confirm they update and gracefully degrade (e.g. codec/device lookup failure hides the badge instead of showing garbage).
