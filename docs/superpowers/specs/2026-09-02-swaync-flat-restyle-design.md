# sqlch-gui → swaync flat restyle

**Date:** 2026-09-02
**Status:** approved, ready for implementation plan

## Problem

sqlch-gui's current "paper-cutout" aesthetic (established in the
2026-07-26 restyle) diverged from the direction Phil's system-wide swaync
styling has since settled into. His hand-tuned `~/.config/swaync/style.css`
is a restrained flat treatment; sqlch-gui still carries SVG paper-grain
texture on every surface, 160° diagonal gradients, letterpress multi-layer
`text-shadow` on all text, hard-offset `cutout()` shadows on *every*
element, tilted decorative chrome, a matted picture-frame album art, and
Cairo-drawn torn-paper / ribbon / pennant shapes.

This restyle brings sqlch-gui in line with the swaync look while keeping
its structure, its live `palette.sh` re-skin, and its multi-color accent
usage.

## Reference

`~/.config/swaync/style.css` — the target. Key moves observed there:

- Flat `#181616` module fills, no gradient, no texture
- Hairline borders: `1px solid alpha(#e6e6e6, 0.15)`
- One soft drop: `box-shadow: 0 1px 1px rgba(0,0,0, 0.55)`
- Recessed `inset` shadows for slider troughs and the session tray
- Radii: 18 (shell) / 12 (cards, trays) / 7 (buttons, chips)
- Section breaks = a hairline top-rule + a small engraved uppercase
  label, left-set — **no box frame** around groups
- `ROOT` (`#8a7070`) accent used sparingly (active / highlight / critical)
- `text-shadow: none` everywhere
- The hard-offset shadow (`3px 4px 0 0`) survives **only** on the outer
  `.control-center` shell, with a very faint SVG fiber-noise (~0.06 alpha)

## Direction (decided during brainstorming)

1. **Full flat translation** — strip the SVG texture, the diagonal
   gradients, and all letterpress `text-shadow`. Every inner element
   becomes flat fill + hairline border + one soft drop. The hard-offset
   `cutout` shadow survives only on the outer window frame.
2. **Flatten all Cairo widgets** — RecordBubble, TornSeparator,
   RibbonBanner, PennantTag all lose their papercraft shapes. VolumeMeter,
   the NavColumn monitor glyph, and EqStrip stay as shapes but are
   recolored flat.
3. **Keep the multi-color accents** — `PIANO` (gold), `SEVENTH` (green),
   `FORTE` stay where they are used today; only *how* they are painted
   flattens (solid fill, no gradient, no emboss).
4. **Fonts** — JetBrains Mono for all chrome; a proportional face
   (`Inter` / `system-ui`) for the Now Playing track title and artist only.
5. **Frame** — match swaync's shell: single `3px 4px 0 0` ink hard-offset,
   18px radius, hairline border, faint fiber-noise (~0.06 alpha) on the
   shell only.

## Palette mapping

All colors resolve from `~/.config/waybar/palette.sh` at runtime (the
current-generation "orca"-style schema). Never hardcode hex; the file
watch in `window.py` already re-runs `load_custom_css()` on palette
change and that behavior is preserved.

| swaync literal        | palette key   | role                                                    |
|-----------------------|---------------|---------------------------------------------------------|
| `#181616`             | `STAGE`       | card / module fills                                     |
| `#2e292a`             | `WING`        | shell bg, button fills, hover bg                        |
| `#0d0c0c`             | `DIM`         | recessed troughs, pressed/checked bg, entry bg          |
| `#e6e6e6`             | `SCORE`       | primary text; `rgba(SCORE, 0.14)` hairline borders      |
| `#bfbfbf`             | `LYRIC`       | secondary text, icons, seam grab bar                    |
| `#8c8c8c`             | `REST`        | disabled text, placeholders                             |
| `#8a7070`             | `ROOT`        | primary accent (active / highlight / critical / focus)  |
| `rgba(0,0,0, 0.55)`   | `STAFF` + `STAFF_A_DROP`      | soft outer drop                          |
| `rgba(0,0,0, 0.30)` inset | `STAFF` + `STAFF_A_INSET_BOT` | trough / tray recess                 |
| `rgba(0,0,0, 0.65)` inset | `STAFF` + `0.6`              | checked / active-pressed recess       |
| shell border `alpha(#e6e6e6, 0.55)` | `SCORE` + `STAFF_A_OUTER` | frame border                       |

Retained multi-color accents:

- `SEVENTH` (green) — `.station-row.active` tint, `.station-live` text
- `PIANO` (gold) — `.control-btn.primary` idle fill
- `FORTE` — `.control-btn.primary` hover, `RecordBubble` armed state,
  `.tech-badge.rec-badge`, VolumeMeter hot/boost pips
- `ROOT` — everything else that was accented

### `palette.py` changes

`_DEFAULTS` gains keys so the Rosé-Pine-Moon fallback still resolves:
`DIM`, `LYRIC`, `STAFF_A_OUTER`, `STAFF_A_DROP`, `STAFF_A_HOVER`,
`STAFF_A_INSET_TOP`, `STAFF_A_INSET_BOT`, `STAFF_A_BORDER`, `MEASURE`,
`TEMPO`. Fallback values chosen to sit sensibly against the existing
Rosé-Pine-Moon defaults (e.g. `DIM` ≈ `#1a1828`, `LYRIC` ≈ `#c9c5da`,
alphas matching the orca schema's numbers).

## Shared CSS vocabulary (`ui/common.py`)

Replaces the `cutout()` / `sheen` / `svg_tactile_filter` / diagonal-
gradient helpers. Remove `sheen` and the per-element grain entirely;
keep a single faint shell-only noise variant; keep `cutout()` but use it
**only** in `.popup-window`.

- `hairline` = `1px solid rgba({score_rgb}, 0.14)`
- `drop` = `0 1px 1px rgba({staff}, {staff_a_drop})` — the only outer
  shadow on inner elements
- `recess` = `inset 0 1px 2px rgba({staff}, {staff_a_inset_bot})`
- `press` = `inset 0 1px 3px rgba({staff}, 0.6)`
- Radii: **18** shell · **12** cards, plates, trays, info-panel ·
  **7** buttons, chips, rows, entries, small badges
- **No `text-shadow` on any class**
- Font stacks (inlined, GTK CSS custom props are unreliable):
  - mono: `"JetBrains Mono", "Courier New", monospace` — base `window`,
    all chrome, headers, badges, pills, buttons, `.info-line`,
    `.station-freq`, `.section-rule`, `.brand-tag`, context menu
  - proportional: `"Inter", "system-ui", sans-serif` — `.meta-title`,
    `.meta-artist` only
  - base size from `TEMPO` (12px)

## Window frame

`.popup-window`:

- `background-color: {WING}`
- faint fiber-noise SVG at ~0.06 alpha (shell only), no linear gradient
- `border-radius: 18px`
- `border: 1px solid rgba({score_rgb}, {staff_a_outer})`
- `box-shadow: {cutout(3, 4)}` → `3px 4px 0 0 rgba({staff}, {staff_a_drop})`
- drops the current double `6px 6px 0 3px … , 10px 10px 0 3px …` stack
  and the full-strength grain + 165° gradient

## Section headers

`RibbonBanner` (in `ui/banner.py`) stops being a `Gtk.Overlay` +
`Gtk.DrawingArea`. It becomes a thin container exposing the same public
API so callers are untouched:

- constructor `RibbonBanner(text: str, gold: bool = False)`
- `set_text(text: str)`
- internally: a `Gtk.Box` holding one `Gtk.Label` with css class
  `section-rule` (and `section-rule-gold` when `gold=True`)

`.section-rule` CSS: `border-top: 1px solid rgba({score_rgb}, 0.13)`,
`margin: 20px 4px 8px`, `padding-top: 8px`; label `10px / 700 /
text-transform: uppercase / letter-spacing: 0.14em`, color `LYRIC`
(`ROOT` for `-gold`).

`RibbonBanner.TAIL_H` and the `_on_draw` / `_resize_canvas` internals are
removed. `station_list.py` (`RibbonBanner(g_name)`) and `discover.py`
(`RibbonBanner("Browse Categories", gold=True)`) need no call-site change,
though surrounding margins may want a light trim once the box frame is
gone.

## Cairo widgets

### `TornSeparator` (`ui/banner.py`)

Keep the class, the orientation handling, the grab/grabbing cursor, and
its role as the window's drag target. Rewrite `_on_draw` to paint a
recessed seam instead of a tear:

- fill the strip `STAGE`
- a 1px hairline (`rgba(SCORE, 0.15)`) down the edge facing the drawer
- a short centered grab bar: 2px rounded line, `LYRIC` at ~0.55 alpha,
  ~46px long (same length the current grab cue uses)

Delete `_tear_points`, `_BODY`, and the shadow-offset path work.

### `PennantTag` (`ui/banner.py`)

Replace the `Gtk.Overlay` + Cairo notch with a plain label-bearing
widget (a `Gtk.Label` subclass, or `Gtk.Box` + `Gtk.Label`) so
`isinstance(widget, PennantTag)` in `station_list.py` still works.

- constructor `PennantTag(text: str, country: bool = False)` unchanged
- css class `tag-chip` (+ `country` modifier)
- `.tag-chip`: `DIM` fill, `hairline`, `border-radius: 7px`, mono,
  `0.72em`, `LYRIC`; `.country` swaps to `SOTTO` text or a subtle tint
- `NOTCH` and `_on_draw` removed

### `RecordBubble` (`ui/controls.py`)

Keep the class, its two signals, `MODES`, `set_state()`, the daemon-
pushed state model, and the left/right click gestures. Rewrite `_on_draw`
to a flat treatment:

- a `34px` circle: fill `WING` idle, `FORTE` armed
- 1px hairline ring (`rgba(SCORE, 0.15)`)
- centered record glyph — a small filled square (~8px) — `LYRIC` idle,
  `SCORE` armed
- no radial gradients, no glow, no hardcoded RGB literals; the armed
  color comes from `palette.load()["FORTE"]`

### `VolumeMeter` (`ui/controls.py`)

Keep the segmented VU model, the click-to-jump, scroll-to-nudge, and the
120% boost overflow pip. Restyle `_on_draw`:

- paint a `DIM` rounded trough behind the whole pip strip (reads as
  recessed, matching swaync's slider troughs)
- unfilled pips: `rgba(SCORE, 0.12)`
- filled pips: the existing `SEVENTH` → `FORTE` green-to-hot ramp, at
  full alpha, flat (no rounded-bar highlight tricks beyond the existing
  `_rounded_bar`)
- boost pip: `FORTE`

### `NavColumn._draw_display` (`ui/controls.py`)

The hand-drawn monitor glyph stays. Swap its stroke color to `SCORE`
when Mini is active / `REST` otherwise, matching the new `.nav-btn`
foreground (was `SHADOW` / `REST`).

### `EqStrip` (`ui/eq_strip.py`)

Shape unchanged. Re-check the `ROOT` → `SEVENTH` bead ramp against the
new flat `.station-row` fill; adjust only if it fails to read.

## Element-level flattening (`ui/common.py`)

Every class below loses its gradient, grain, `cutout`, transforms, and
`text-shadow`, and is rebuilt as `flat fill + hairline + drop`:

- `.nav-btn` / `:hover` / `.active` — hover lightens toward `WING`,
  active is `ROOT` fill with `SHADOW` text; **remove `scale()` and
  `translateY` transforms**
- `.card`, `.list-plate`, `.list-header`, `.info-panel` (+ `.stale`),
  `.nav-row`
- `.station-row` / `:hover` / `.active` — hover `WING`, active flat
  `SEVENTH` tint
- `.station-freq`, `.station-live`, `.info-line` — mono, flat, no emboss
- `.control-btn` / `:hover` / `:active` / `.primary` — primary idle
  `PIANO`, primary hover `FORTE`
- `.menu-btn` (+ `:hover` / `:active` / `.destructive-action`)
- `.field-entry` (+ `:focus-within`) — `DIM` fill, focus ring `ROOT`
- `.search-btn` (+ `:hover`)
- `.tech-badge` / `.tag-chip` (+ `.rec-badge`), `.small-badge`
- `.meta-title`, `.meta-artist`, `.meta-genre`, `.thread-label`,
  `.ribbon-label` → folded into `.section-rule`, `.pennant-label` →
  folded into `.tag-chip`, `.pennant-btn`, `.knob-tag`, `.brand-tag`
- `popover.context-menu > contents` / `> arrow` / `.context-menu *`
- `.cover-art` — drop the matted `inset` ROOT/ink rings → `hairline` +
  `drop`; `.cover-glyph` and `.corner-tag` / `.corner-tag-left` lose
  their `rotate()`

## Files touched

| file | change |
|---|---|
| `sqlch_gui/ui/common.py` | full CSS rewrite (the bulk) |
| `sqlch_gui/ui/banner.py` | `RibbonBanner` + `PennantTag` de-Cairo'd; `TornSeparator` draw simplified |
| `sqlch_gui/ui/controls.py` | `RecordBubble` + `VolumeMeter` flat draw; `NavColumn` glyph color |
| `sqlch_gui/ui/eq_strip.py` | bead color re-check |
| `sqlch_gui/palette.py` | `_DEFAULTS` additions |
| `sqlch_gui/ui/now_playing.py`, `station_list.py`, `discover.py` | light margin/spacing trims only, if needed once frames are gone |

Live `palette.sh` file-watch re-skin (`window.py`) is untouched and must
keep working.

## Verification

No GUI tests exist today.

1. **Smoke test** (new, `tests/test_gui_style.py` or similar):
   - `palette.load()` returns the new keys with the `_DEFAULTS` fallback
   - `common.load_custom_css()` builds a `Gtk.CssProvider` and
     `load_from_string` accepts the generated CSS without raising
   - the flattened widgets (`RibbonBanner`, `PennantTag`, `RecordBubble`,
     `VolumeMeter`, `TornSeparator`) construct without error
   - run headless (`xvfb-run` / offscreen) if the environment allows;
     if GTK can't init, skip with a clear marker
2. **Live visual check** — working-tree dev instance via the layer-shell
   launch procedure (copy env from the installed wrapper, `LD_PRELOAD`
   `libgtk4-layer-shell.so`, `/home/prepko/sqlch` first on `PYTHONPATH`;
   kill prior instance by PID in a separate command). Phil screenshots
   Now Playing + the Library drawer + Discover across at least two
   palettes (a dark one and a lighter one) to confirm the mapping tracks.

## Out of scope

- No structural / layout changes (drawer mechanics, panel composition,
  nav model all stay)
- No new features
- No changes to the TUI or CLI
- `auto-theme.py` and the generated per-theme swaync files are not
  touched — sqlch adapts via `palette.sh` at runtime, not regeneration
