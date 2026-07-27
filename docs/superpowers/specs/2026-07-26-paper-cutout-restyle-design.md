# Paper-cutout restyle (drop the stitching motif)

## Goal

Retire the dashed-thread / `hem()` "quilted fabric" motif in
`sqlch_gui/ui/common.py` and replace it everywhere with a flat paper-cutout
look: solid ink outline + a crisp hard-edged offset shadow (no blur, no
dashes). `.popup-window` already uses this formula for the outer window
frame; this extends it to every inner patch so the whole UI reads as one
consistent style instead of "floating window, stitched patches inside."

## Scope

Every class currently using `border: Npx dashed {thread}` or the `hem()`
helper gets converted:

`.popup-window`, `.nav-btn` (+hover/active), `.card`, `.list-plate`,
`.list-header`, `.station-row` (+hover/active), `.tech-badge`/`.tag-chip`
(+hover), `.brand-tag`, `popover.context-menu > contents`, `.context-menu
entry` (+focus-within), `.menu-btn` (+hover/active/destructive-action),
`.field-entry` (+focus-within), `.art-card-back`.

(`tech-badge`/`rec-badge` alone are dead code — no widget applies them —
but they share a rule with the live `.tag-chip`, so they get swept up in
the same edit rather than split out.)

`.corner-tag`, `.corner-tag-left/right/rec/flip` currently already use a
hard flat offset shadow (`0 2px 0 rgba(staff,0.4)`) with no blur and no
outline. They gain a matching solid ink outline for consistency (every
element outlined, not just the top-level patches).

## New formula

Retire `thread`, `get_adaptive_thread()`, `hem()`, `hem_c`, `shade_c`.
Replace with a small helper:

```python
def cutout(dx: int, dy: int) -> str:
    """Hard-edged offset duplicate, paired with a solid ink border."""
    return f"{dx}px {dy}px 0 0 {outline}"
```

- Small elements (nav buttons, station rows, tags, chips, menu items,
  field entries): `border: 2px solid {outline}` + a 2-3px `cutout()`
  offset.
- The two "floating tier" pieces (`.popup-window`, `.card`) keep their
  existing larger multi-layer offsets (6-10px), since they're meant to
  read as sitting a level above the smaller patches.
- The invisible-border-at-rest trick is preserved for hover/active states
  that currently rely on it (e.g. `.nav-btn` keeps `border: 2px solid
  transparent` at rest so hover/active don't shift layout) — just `solid`
  instead of `dashed`.

## What's kept, untouched

- `lite_c` letterpress text-shadow bevels on titles/labels (`.meta-title`,
  `.meta-artist`, `.station-freq`, etc.) — a different motif (ink emboss on
  text), not stitching.
- `slight` / `slight_lift` / `slight_press` soft ambient shadows — layered
  underneath the new hard offset for some grounding, same as
  `.popup-window` already does.
- `staff` / `shadow` ground-shadow color for the outer ambient layer on
  the two floating-tier pieces.
- Ink outline color stays `{outline}` (palette `SHADOW`), which per
  existing convention stays dark on every generated palette.

## Verification

- Launch the working-tree dev instance (per the existing launch memory)
  and visually check: nav row, station list, control row, context menu,
  cover-art back-plate.
- Spot-check against at least one light-background palette and one
  dark-background palette (e.g. the current "A marble" theme) to confirm
  the solid ink outline still reads against both.
- `python3 -c "import ast; ast.parse(...)"` syntax check (no test suite
  covers CSS strings directly).
