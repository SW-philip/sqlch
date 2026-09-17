# sqlch-gui Depth Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sqlch-gui's flat stylesheet actually read as having depth, across every palette, without reverting the 2026-09-02 flat restyle.

**Architecture:** A CIE76-based "layer ladder" guarantees WING/STAGE/DIM (shell/card/recessed-plate fills) are perceptually distinct from each other on every palette; the shared `drop`/`recess` shadow tokens get louder; the empty cover-art void gets the same recess treatment as sliders instead of a flat painted square. Colour math lives in a new `sqlch_gui/colormath.py` (mirrors `~/nixos/scripts/theme_lib/colormath.py`'s public/private split) rather than being folded into `palette.py` — keeps the pure math independently testable and `palette.py` focused on I/O. This is a refinement of the design spec's file layout, not a scope change.

**Tech Stack:** Python 3.11+, GTK4 CSS (via `Gtk.CssProvider`), `unittest` (this repo's test convention — no pytest dependency).

## Global Constraints

- Repo: `~/sqlch` (separate git remote from `~/nixos`; do not touch `~/nixos` files).
- ΔE floor is 25.0 (CIE76) — this repo's established "clearly different" bar (see `~/nixos/CLAUDE.md` "Theme engine" and `~/nixos/scripts/theme_lib/colormath.py` docstrings).
- No new Python dependencies.
- No `linear-gradient`, no `text-shadow`, no papercraft/Cairo-shape reintroduction anywhere touched by this plan — the 2026-09-02 flat direction stands (`docs/superpowers/specs/2026-09-02-swaync-flat-restyle-design.md`).
- Raw `WING`/`STAGE`/`DIM` palette values must never be mutated — only new derived keys are added. Other consumers of `palette.sh` (swaync, waybar, hyprlock, greeter, all in `~/nixos`) are untouched by this work.
- Test runner: `cd ~/sqlch && python3 -m unittest <module> -v` (verified working; no pytest installed in the dev shell).

---

### Task 1: Colour-math + layer ladder (`sqlch_gui/colormath.py`)

**Files:**
- Create: `sqlch_gui/colormath.py`
- Test: `tests/test_colormath.py`

**Interfaces:**
- Produces (used by Task 2):
  - `colormath.DE_FLOOR: float` = `25.0`
  - `colormath.srgb_to_lab(hex_color: str) -> tuple[float, float, float]`
  - `colormath.delta_e_cie76(hex_a: str, hex_b: str) -> float`
  - `colormath.apply_ladder(colors: dict) -> dict` — reads `colors['WING']`,
    `colors['STAGE']`, `colors['DIM']`, `colors['SCORE']` directly (contract:
    caller passes a dict already merged with `palette._DEFAULTS`, so this
    never needs a fallback — a `KeyError` here means the caller broke the
    contract, not a case to paper over); returns
    `{'WING_EFF': str, 'STAGE_EFF': str, 'DIM_EFF': str}` (hex strings).

**Algorithm (verified by hand against real theme data — see below):**

`apply_ladder`:
1. Sort the three roles `('WING', 'STAGE', 'DIM')` ascending by L\*
   (`srgb_to_lab(colors[role])[0]`).
2. The darkest role is the anchor — its `_EFF` value is its raw value,
   unchanged.
3. Walk the remaining roles from darkest to lightest. For each, push it
   lighter (via `_push_lighter`) until its ΔE(CIE76) against **every
   already-finalized (darker) role's `_EFF` value** is ≥ `DE_FLOOR` — not
   just its immediate neighbor. (A neighbor-only check was tried first and
   verified broken: on `indigo-rose` and `moss-violet` palette data, fixing
   only the two sort-adjacent gaps left the third — WING vs DIM — under the
   floor, at 17.0 and 15.0 respectively. Checking against *all* finalized
   anchors, not just the nearest one, fixes this.)

`_push_lighter(hex_color, anchors: list[str], score_hex: str) -> str`:
- Convert to HSL. Loop up to 40 times: each step, hue-shift +0.02 (mod 1.0),
  saturation -0.02 (floor 0), lightness +0.015 (cap 1.0) — the same
  direction-compensated push `~/nixos/scripts/theme_lib/colormath.py`'s
  `_adjust_color` uses when lightening (warm hue shift, trimmed saturation,
  to avoid a neon result).
- Stop early once `delta_e_cie76(hex_color, a) >= DE_FLOOR` holds for every
  `a` in `anchors`.
- Clamp: also stop once `srgb_to_lab(hex_color)[0] >= srgb_to_lab(score_hex)[0] - 10`
  — never push a fill within 10 L\* of the text colour. This is a soft,
  best-effort clamp: on a palette so monochrome that neither the ΔE floor
  nor useful separation is reachable before hitting it, the loop just stops
  where it is (Task 3 covers detecting and reporting this case, not failing
  on it).

**Verified real-world behavior (hand-run, see below for the exact figures —
use these as test fixtures):**

| Palette | Before (worst pair) | After (all 3 pairs) |
|---|---|---|
| `slate-lavender` (`WING #5c6a71 STAGE #4d5358 DIM #45494c`) | STAGE-DIM ΔE 4.4 | 26.1 / 52.1 / 26.1 |
| Rosé Pine Moon default (`WING #393552 STAGE #2a273f DIM #1a1828`) | STAGE-DIM ΔE 9.2 | 26.4 / 50.5 / 25.1 |
| `indigo-rose` (`WING #3d4671 STAGE #303254 DIM #2a2b46`) | STAGE-DIM ΔE 5.5 | 26.4 / 52.1 / 27.1 |
| `moss-violet` (`WING #6eb076 STAGE #5a9b69 DIM #558c61`) | STAGE-DIM ΔE 7.0 | 25.0 / 46.4 / 28.6 |

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_colormath.py
import unittest

from sqlch_gui import colormath


class TestColorMath(unittest.TestCase):
    def test_delta_e_cie76_known_value(self):
        # sanity-check the ported Lab conversion against a hand-verified figure
        self.assertAlmostEqual(
            colormath.delta_e_cie76("#5c6a71", "#4d5358"), 9.49, places=1
        )

    def test_srgb_to_lab_black_and_white(self):
        l_black, _, _ = colormath.srgb_to_lab("#000000")
        l_white, _, _ = colormath.srgb_to_lab("#ffffff")
        self.assertAlmostEqual(l_black, 0.0, places=1)
        self.assertAlmostEqual(l_white, 100.0, places=1)


class TestApplyLadder(unittest.TestCase):
    def _colors(self, wing, stage, dim, score="#ffffff"):
        return {"WING": wing, "STAGE": stage, "DIM": dim, "SCORE": score}

    def test_ladder_fixes_slate_lavender(self):
        eff = colormath.apply_ladder(
            self._colors("#5c6a71", "#4d5358", "#45494c")
        )
        self.assertGreaterEqual(
            colormath.delta_e_cie76(eff["WING_EFF"], eff["STAGE_EFF"]), 25.0)
        self.assertGreaterEqual(
            colormath.delta_e_cie76(eff["WING_EFF"], eff["DIM_EFF"]), 25.0)
        self.assertGreaterEqual(
            colormath.delta_e_cie76(eff["STAGE_EFF"], eff["DIM_EFF"]), 25.0)

    def test_ladder_fixes_indigo_rose_skip_pair(self):
        # Regression case: a neighbor-only push leaves WING vs DIM under the
        # floor (17.0) even though the two sort-adjacent pairs clear it.
        eff = colormath.apply_ladder(
            self._colors("#3d4671", "#303254", "#2a2b46")
        )
        self.assertGreaterEqual(
            colormath.delta_e_cie76(eff["WING_EFF"], eff["DIM_EFF"]), 25.0)

    def test_ladder_is_identity_when_already_distinct(self):
        eff = colormath.apply_ladder(
            self._colors("#000000", "#808080", "#ffffff")
        )
        self.assertEqual(eff["WING_EFF"], "#000000")
        self.assertEqual(eff["STAGE_EFF"], "#808080")
        self.assertEqual(eff["DIM_EFF"], "#ffffff")

    def test_ladder_never_crosses_score_lightness(self):
        # WING/STAGE/DIM all sit close together AND close to SCORE -- the
        # floor is unreachable, so the clamp must win instead of overshooting.
        colors = self._colors("#101010", "#121212", "#0e0e0e", score="#2a2a2a")
        eff = colormath.apply_ladder(colors)
        score_l = colormath.srgb_to_lab(colors["SCORE"])[0]
        for key in ("WING_EFF", "STAGE_EFF", "DIM_EFF"):
            self.assertLess(colormath.srgb_to_lab(eff[key])[0], score_l)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/sqlch && python3 -m unittest tests.test_colormath -v`
Expected: `ModuleNotFoundError: No module named 'sqlch_gui.colormath'`

- [ ] **Step 3: Write `sqlch_gui/colormath.py`**

```python
"""Minimal, dependency-free CIE76 colour math and the layer-contrast ladder.

Mirrors the public/private split of ~/nixos/scripts/theme_lib/colormath.py
(that module can't be imported directly -- sqlch-gui is a separate repo with
its own dependency surface) but keeps only what the ladder needs: no
ColorHunt parsing, no green-saturation-ceiling accent helper.
"""
import math

DE_FLOOR = 25.0

_LADDER_ROLES = ("WING", "STAGE", "DIM")


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        hue = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return hue / 6, s, l


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    h = h % 1.0
    s = max(0.0, min(1.0, s))
    l = max(0.0, min(1.0, l))
    if s == 0:
        v = round(l * 255)
        return f"#{v:02x}{v:02x}{v:02x}"

    def _hue(p, q, t):
        t %= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r, g, b = _hue(p, q, h + 1 / 3), _hue(p, q, h), _hue(p, q, h - 1 / 3)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _srgb_to_linear(v: float) -> float:
    c = v / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb_to_lab(hex_color: str) -> tuple[float, float, float]:
    """sRGB hex -> CIE L*a*b* (D65 reference white, 2-degree observer)."""
    h = hex_color.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def _f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = _f(x), _f(y), _f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e_cie76(hex_a: str, hex_b: str) -> float:
    """CIE76 colour difference: Euclidean distance in L*a*b*.

    ~2.3 is a just-noticeable difference; >= 25 reads as "clearly
    different" (this repo's distinctness bar, matching ~/nixos)."""
    la, lb = srgb_to_lab(hex_a), srgb_to_lab(hex_b)
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(la, lb)))


def _push_lighter(hex_color: str, anchors: list[str], score_hex: str) -> str:
    """Step hex_color's HSL lightness up, hue-compensated (warm shift,
    saturation trim -- the same compensation ~/nixos's palette-gen adjust
    helper applies when lightening), until it clears DE_FLOOR against every
    anchor or the clamp against score_hex's lightness is reached.
    Best-effort: returns the last step even if the floor was never reached."""
    h, s, l = _hex_to_hsl(hex_color)
    score_lstar = srgb_to_lab(score_hex)[0]
    for _ in range(40):
        if all(delta_e_cie76(hex_color, a) >= DE_FLOOR for a in anchors):
            break
        if srgb_to_lab(hex_color)[0] >= score_lstar - 10:
            break
        h = (h + 0.02) % 1.0
        s = max(0.0, s - 0.02)
        l = min(1.0, l + 0.015)
        hex_color = _hsl_to_hex(h, s, l)
    return hex_color


def apply_ladder(colors: dict) -> dict:
    """Guarantee pairwise ΔE(CIE76) >= DE_FLOOR among WING/STAGE/DIM without
    mutating the raw palette keys (those stay shared with swaync/waybar/
    hyprlock/greeter via palette.sh -- see docs/superpowers/specs/
    2026-09-17-sqlch-gui-depth-pass-design.md). Returns new '<ROLE>_EFF' keys.

    Contract: colors must already contain WING/STAGE/DIM/SCORE -- every
    caller in this codebase passes a dict merged from palette._DEFAULTS
    (palette.load() always starts from dict(_DEFAULTS)), so this indexes
    directly and lets a KeyError surface a genuine caller bug rather than
    silently falling back to a nonsense value."""
    score = colors["SCORE"]
    raw = {r: colors[r] for r in _LADDER_ROLES}
    order = sorted(_LADDER_ROLES, key=lambda r: srgb_to_lab(raw[r])[0])

    eff = {order[0]: raw[order[0]]}
    for i in range(1, len(order)):
        role = order[i]
        anchors = [eff[r] for r in order[:i]]
        eff[role] = _push_lighter(raw[role], anchors, score)

    return {f"{r}_EFF": eff[r] for r in _LADDER_ROLES}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/sqlch && python3 -m unittest tests.test_colormath -v`
Expected: `OK` (6 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/sqlch
git add sqlch_gui/colormath.py tests/test_colormath.py
git commit -m "feat(sqlch-gui): CIE76 layer-contrast ladder for WING/STAGE/DIM

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Wire the ladder into the stylesheet, strengthen shadows, socket the cover-art void

**Files:**
- Modify: `sqlch_gui/ui/common.py:1-489` (specifically the `_build_css`
  function and its `drop`/`recess` token definitions, and the `.cover-art`
  rule)
- Modify: `tests/test_gui_style.py` (extend `TestFlatStylesheet`)

**Interfaces:**
- Consumes: `colormath.apply_ladder(colors: dict) -> dict` from Task 1.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gui_style.py` (inside `TestFlatStylesheet`, and a new
class after it):

```python
    def test_card_and_plate_fills_use_ladder_output(self):
        from sqlch_gui.ui import common
        from sqlch_gui import colormath
        colors = dict(palette._DEFAULTS)
        colors.update(WING="#5c6a71", STAGE="#4d5358", DIM="#45494c")
        eff = colormath.apply_ladder(colors)
        css = common._build_css(colors)
        self.assertIn(f"background-color: {eff['STAGE_EFF']}", css)
        self.assertIn(f"background-color: {eff['WING_EFF']}", css)
        self.assertIn(f"background-color: {eff['DIM_EFF']}", css)
        # the raw, un-laddered STAGE hex must not leak through as a fill
        self.assertNotIn("background-color: #4d5358", css)


class TestDepthPass(unittest.TestCase):
    def test_drop_shadow_is_stronger_than_original(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        self.assertIn("box-shadow: 0 2px 3px", css)
        self.assertNotIn("box-shadow: 0 1px 1px", css)

    def test_recess_shadow_is_stronger_than_original(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        self.assertIn("inset 0 2px 4px", css)
        self.assertNotIn("inset 0 1px 2px", css)

    def test_cover_art_uses_recess_not_drop(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        cover_rule = css.split(".cover-art {")[1].split("}")[0]
        self.assertIn("inset", cover_rule)
```

(`test_gui_style.py` already imports `from sqlch_gui import palette` at
module level — no new import needed there beyond the local `common`/
`colormath` imports shown above, matching the file's existing per-test
import style.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/sqlch && python3 -m unittest tests.test_gui_style -v`
Expected: `FAIL` — `test_card_and_plate_fills_use_ladder_output`,
`test_drop_shadow_is_stronger_than_original`,
`test_recess_shadow_is_stronger_than_original`,
`test_cover_art_uses_recess_not_drop` all fail (old fills/shadow values
still in place).

- [ ] **Step 3: Wire the ladder and strengthen tokens in `common.py`**

In `sqlch_gui/ui/common.py`, add the import at the top (alongside the
existing `from .. import palette`):

```python
from .. import colormath
```

Replace the `stage`/`wing`/`dim` assignments inside `_build_css` (currently):

```python
    stage = colors.get('STAGE', '#2a273f')
    wing = colors.get('WING', '#393552')
    dim = colors.get('DIM', '#1a1828')
```

with:

```python
    ladder = colormath.apply_ladder(colors)
    stage = ladder['STAGE_EFF']
    wing = ladder['WING_EFF']
    dim = ladder['DIM_EFF']
```

Every other line in `_build_css` already references `{stage}`/`{wing}`/
`{dim}` by these same local variable names (they're f-string
interpolations) — no other line needs to change for the ladder to take
effect everywhere: `.popup-window`, `.nav-row`, `.nav-btn`, `.card`,
`.cover-art`, `.list-plate`, `.station-row`, `.control-btn`,
`.tech-badge`/`.tag-chip`, `.small-badge`, `.menu-btn`, `.field-entry`,
`.search-btn`, `.load-more-row`, `.info-panel`, and the `popover.context-menu`
rules all pick up the ladder-derived fills automatically.

Then widen the shared shadow tokens (currently):

```python
    hairline = f"1px solid rgba({score_rgb}, 0.14)"
    rule = f"1px solid rgba({score_rgb}, 0.13)"
    drop = f"0 1px 1px rgba({staff}, {a_drop})"
    recess = f"inset 0 1px 2px rgba({staff}, {a_inset})"
    press = f"inset 0 1px 3px rgba({staff}, 0.6)"
```

to:

```python
    hairline = f"1px solid rgba({score_rgb}, 0.14)"
    rule = f"1px solid rgba({score_rgb}, 0.13)"
    drop = f"0 2px 3px rgba({staff}, {a_drop})"
    recess = f"inset 0 2px 4px rgba({staff}, {a_inset})"
    press = f"inset 0 1px 3px rgba({staff}, 0.6)"
```

(`press` — the active/pressed-button state — is unchanged; only the at-rest
`drop`/`recess` tokens get louder.)

Finally, switch `.cover-art` from `drop` to `recess` (currently):

```python
    .cover-art {{
        background-color: {wing};
        border-radius: 12px;
        border: {hairline};
        min-width: 220px;
        min-height: 220px;
        box-shadow: {drop};
    }}
```

to:

```python
    .cover-art {{
        background-color: {wing};
        border-radius: 12px;
        border: {hairline};
        min-width: 220px;
        min-height: 220px;
        box-shadow: {recess};
    }}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/sqlch && python3 -m unittest tests.test_gui_style -v`
Expected: `OK` (all tests, old + new)

- [ ] **Step 5: Run the full existing suite to check for regressions**

Run: `cd ~/sqlch && python3 -m unittest discover tests -v 2>&1 | tail -20`
Expected: `OK` — in particular `test_css_parses_without_error_on_every_palette`
and `test_no_paper_cutout_vocabulary` (both in `test_gui_style.py`) must
still pass unchanged, confirming the ladder output is still valid CSS and
still carries no gradient/text-shadow.

- [ ] **Step 6: Commit**

```bash
cd ~/sqlch
git add sqlch_gui/ui/common.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): wire layer-contrast ladder into the stylesheet, deepen shadows, socket the cover-art void

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Cross-theme sweep (warn, don't fail)

**Files:**
- Create: `tests/test_palette_theme_sweep.py`

**Interfaces:**
- Consumes: `colormath.apply_ladder`, `colormath.delta_e_cie76` from Task 1;
  `sqlch_gui.palette.load(path)` (existing, unmodified).

Purpose: confirm the ladder actually holds across every real theme this
system ships, not just the four hand-picked fixtures in Task 1 — mirroring
`emit_colors.py`'s non-fatal-warning pattern in `~/nixos`. This test lives
in the `sqlch` repo but reads theme files from `~/nixos/themes/**/
palette-*.sh`, a path that only exists on Phil's machines where both repos
are checked out side by side — so it must skip cleanly, not fail, when that
directory isn't present (a clone of this repo alone, or CI, won't have it).

- [ ] **Step 1: Write the test**

```python
# tests/test_palette_theme_sweep.py
import glob
import os
import sys
import unittest
from pathlib import Path

from sqlch_gui import colormath, palette

_THEMES_ROOT = Path(
    os.environ.get("SQLCH_GUI_THEMES_ROOT", Path.home() / "nixos" / "themes")
)


@unittest.skipUnless(_THEMES_ROOT.is_dir(), f"{_THEMES_ROOT} not present")
class TestPaletteThemeSweep(unittest.TestCase):
    def test_ladder_holds_or_warns_across_every_theme(self):
        paths = sorted(glob.glob(str(_THEMES_ROOT / "**" / "palette-*.sh"), recursive=True))
        self.assertGreater(len(paths), 0, f"no palette-*.sh files under {_THEMES_ROOT}")

        residual = []
        for path in paths:
            colors = palette.load(path)
            eff = colormath.apply_ladder(colors)
            pairs = [
                ("WING", "STAGE"), ("WING", "DIM"), ("STAGE", "DIM"),
            ]
            for a, b in pairs:
                de = colormath.delta_e_cie76(eff[f"{a}_EFF"], eff[f"{b}_EFF"])
                if de < colormath.DE_FLOOR:
                    residual.append((path, a, b, round(de, 1)))

        if residual:
            sys.stderr.write("sqlch-gui depth-pass: ladder did not fully "
                              "converge on these palettes (clamp reached "
                              "before the DE_FLOOR):\n")
            for path, a, b, de in residual:
                sys.stderr.write(f"  {path}: {a}_EFF vs {b}_EFF DeltaE {de}\n")
        # Non-fatal by design (matches emit_colors.py's warning pattern) --
        # a palette so monochrome the clamp wins before DE_FLOOR is a real
        # possibility, not a bug, and should be eyeballed, not block CI.


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it**

Run: `cd ~/sqlch && python3 -m unittest tests.test_palette_theme_sweep -v`
Expected: `OK`, with the test *reporting* (via stderr) any palette whose
ladder didn't fully converge, rather than failing. Read the stderr output —
if anything is listed, note which palette/pair for the manual eyeball pass
in the Completion checklist below.

- [ ] **Step 3: Commit**

```bash
cd ~/sqlch
git add tests/test_palette_theme_sweep.py
git commit -m "test(sqlch-gui): sweep the ladder across every shipped theme, non-fatal

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Completion

Code-complete once Tasks 1–3 are committed and `python3 -m unittest discover
tests -v` is green end to end. This changes `sqlch-gui`'s Python source, and
the nix package (`~/nixos/pkgs/sqlch/default.nix`) pins it by commit hash
(`rev = "394d75f5f98437fc4727bbd11209de0e349a8ce9"` at time of writing) — so
after pushing this branch to `origin` (`git@github.com:SW-philip/sqlch`),
`~/nixos/pkgs/sqlch/default.nix`'s `rev`/`sha256` need bumping to the new
commit before `nrs` will actually pick it up. That bump is a separate,
one-line change in the `~/nixos` repo — out of scope for this plan, but
required before any of this is visible on surface or desktop.

**Phil's manual checklist, once built:**

1. `sqlch-gui-toggle` (or `sqlch-gui` directly) on `slate-lavender` (current
   theme) — mini view: does the card/nav-row/cover-art now visibly separate
   from the shell? Does the cover-art void read as a recessed socket instead
   of a flat square?
2. Switch to `indigo-rose` or `moss-violet` (`drmis set <theme>`) — same
   checks. These were the two palettes where Task 1's simulation showed the
   ladder working hardest (up to 20 push-steps); confirm the result looks
   like "more depth," not "washed out" or over-desaturated.
3. Switch to a theme the sweep test (Task 3) flagged as not fully converging,
   if any were reported — confirm it at least reads better than before, even
   if not perfect.
4. Rosé Pine Moon (the module's own `_DEFAULTS` — pick whichever shipped
   theme is closest, or run with `SQLCH_GUI_PALETTE=/nonexistent` to force
   the fallback) — confirm the *already-healthy* case didn't get pushed
   somewhere ugly.
5. Station list / library view and Discover view — since the fix is in
   shared CSS classes, spot-check these too, not just the mini view.
