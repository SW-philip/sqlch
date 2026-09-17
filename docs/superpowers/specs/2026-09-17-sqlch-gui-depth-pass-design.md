# sqlch-gui — depth pass

**Date:** 2026-09-17
**Status:** Approved for implementation

## Problem

The 2026-09-02 swaync flat restyle (`2026-09-02-swaync-flat-restyle-design.md`)
deliberately stripped sqlch-gui's papercraft look (SVG grain, diagonal
gradients, letterpress text-shadow, Cairo torn-ribbon/pennant shapes) down to
swaync's restrained flat vocabulary: flat fill + hairline border + one soft
drop shadow. Two and a half weeks later, Phil: "I feel like it's too flat."

Live screenshot (surface, current theme `slate-lavender`) confirms it: the
depth cues from the restyle spec are present in the CSS but barely register.
Two contributors:

1. **Layer contrast.** Every raised surface (`.card`, `.nav-row`,
   `.station-row`, `.list-plate`) is separated from what it sits on by only a
   1px hairline + `0 1px 1px` drop shadow — no guaranteed color distinctness.
   On palettes where the relevant roles sit close in lightness (`slate-lavender`,
   and per the nix-mark-unification memory, also `indigo-rose` and
   `moss-violet`), that separation nearly disappears.
2. **Content.** The 220×220 `.cover-art` square — the single largest shape on
   screen — is a flat `WING`-fill void with a centered music-note glyph
   whenever there's no art, which is most of the time for radio streams. Its
   blankness reads as "no depth" before you even look at the chrome.

Direction (decided in brainstorming): **push harder within the flat
language** — do not reintroduce papercraft/gradients/texture, do not diverge
from the swaync-matched vocabulary. Scope: whole app in one pass (the fix
lives in shared CSS classes, so mini/library/discover all benefit together),
plus the cover-art void.

## Layer-contrast ladder (`sqlch_gui/palette.py`)

The stylesheet nests surfaces in reused pairs — `WING` (shell) behind `.card`/
`.nav-row` (`STAGE`) *and* behind `.list-plate` (`DIM`); `DIM` (plate) behind
`.station-row`/`.list-header` (`STAGE` again, now nested one level deeper);
`STAGE` (card/nav-row) behind `.nav-btn`/`.control-btn` (`WING`). Each of
`WING`/`STAGE`/`DIM` is "outer" in one pair and "inner" in another, so a
single per-role override doesn't work — a small ladder does:

1. Compute each role's L\* (CIE Lab lightness) to get the palette's current
   recessed→raised order among `{WING, DIM, STAGE}`.
2. Walk that order pairwise (2 adjacent gaps for 3 roles) and push the
   more-raised role of any gap with ΔE (CIE76) < 25 — this repo's established
   "clearly different" bar, the same one used for the eww alert-bar colour
   picks — further in its *existing* lightness direction, using a
   hue-compensated HSL adjust (cool-shift + saturation boost when darkening,
   warm-shift + saturation trim when lightening — the same compensation
   `_adjust_color` in `scripts/theme_lib/colormath.py` already applies),
   clamped so the push never crosses `SCORE` (text) lightness.
   All three pairwise relationships the CSS actually nests
   (`WING`↔`STAGE`, `WING`↔`DIM`, `DIM`↔`STAGE`) matter, not just two of
   them — but with only 3 roles, fixing the two *sort-adjacent* gaps is
   sufficient: pushes only ever increase separation and preserve sort order,
   so the third (first-vs-last) gap's L* separation is the sum of the two
   adjacent ones and comes out ≥ 25 automatically once both adjacent gaps do
   (ΔE on these near-neutral panel colors is L*-dominated, so this holds in
   practice, same non-rigorous-but-consistent standard this repo already
   applies to the FIFTH/REST bar picks).
3. Store results as new suffixed keys — `WING_EFF`, `STAGE_EFF`, `DIM_EFF` —
   in the dict `palette.load()` returns, always present (identical to the raw
   value when a role needed no push). Raw `WING`/`STAGE`/`DIM` pass through
   unmodified, so nothing else reading `palette.sh` (swaync, waybar, hyprlock,
   greeter) is affected. This mirrors the explicit precedent in the
   nix-mark-unification memory: a shared-ink contrast problem gets a
   local fix, not a 3-surface palette change for a 1-surface problem — same
   logic, background fills instead of ink.
4. `_build_css` in `ui/common.py` reads the `_EFF` variants for background
   *fills* only. Borders and text keep reading raw `SCORE`/`LYRIC`/etc.,
   unaffected.

**Colour math:** `sqlch-gui` lives in a separate repo from `~/nixos`, so this
gets a small, self-contained, dependency-free port (not a cross-repo import)
of `srgb_to_lab`, `delta_e_cie76`, `_hex_to_hsl`, `_hsl_to_hex`, and
`_adjust_color` into `sqlch_gui/palette.py` — trimmed to just what the ladder
needs (no ColorHunt import, no green-saturation-ceiling helper, those don't
apply here).

## Shadow / recess strength (`sqlch_gui/ui/common.py`)

Every raised surface currently shares one `drop = 0 1px 1px rgba(STAFF,
a_drop)` token — too subtle to register even once fill colour is fixed.
Widen it to `0 2px 3px rgba(STAFF, a_drop)` app-wide (`.card`, `.nav-row`,
`.nav-btn`, `.control-btn`, `.station-row`, `.list-header`, `.menu-btn`,
`.search-btn`, `.load-more-row`). Deepen `recess` (currently `inset 0 1px
2px`) to `inset 0 2px 4px` for `.list-plate`, `.field-entry`, and the new
`.cover-art` recess (below). Same single-shadow flat rule stays: no
gradients, no `text-shadow`, no double-stacked shadows anywhere but the outer
`.popup-window` shell (unchanged).

## Cover-art void (`.cover-art` in `ui/common.py`)

`.cover-art` is a plain `Gtk.Stack` (no Cairo drawing — `now_playing.py`
lines 49–58), so this is a pure stylesheet change. It currently gets
`background-color: WING` + `drop`. Switch it to `background-color: WING_EFF`
+ `recess` (the same inset-trough treatment already used for sliders) instead
of `drop` — it reads as a socket the art drops into rather than a flat
painted square. No new widget, no decorative pattern, no glyph/layout change
— same vocabulary, applied to the biggest flat plane in the app.

## Verification

Since every change above is palette-derived, the real test is whether the
ladder holds across the actual theme set, not just whether `slate-lavender`
looks better.

- A standalone check (script or pytest, matching sqlch-gui's existing test
  pattern) runs `palette.load()` + the ladder derivation against every
  theme's `palette.sh` under `~/nixos/themes/**/`, asserts the ΔE floor holds
  post-derivation for each of the three pairs, and — mirroring
  `emit_colors.py`'s non-fatal pattern — **warns rather than fails** on any
  palette where the clamp is hit before reaching ΔE 25 (report which pairs,
  don't block).
- Manual eyeball, once built: `slate-lavender` (current, known-bad), one more
  of the two other flagged palettes (`indigo-rose` or `moss-violet`), and one
  already-healthy palette (Rosé Pine Moon, the module's own default) — to
  confirm the ladder doesn't needlessly push palettes that were already fine.

## Out of scope

- No papercraft / gradient / diagonal-shading / letterpress text-shadow
  reintroduction — the 2026-09-02 flat direction stands.
- No changes to swaync, waybar, hyprlock, greeter, or any other consumer of
  `palette.sh` — the `_EFF` keys are local to `sqlch_gui/palette.py`.
- No new Python dependencies.
- No widget/layout changes beyond the CSS class swaps above (no new cover-art
  decoration, no glyph resize, no drawer/banner changes).
