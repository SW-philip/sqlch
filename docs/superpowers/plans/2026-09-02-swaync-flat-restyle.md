# sqlch-gui swaync Flat Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle sqlch-gui from its "paper-cutout" look to the flat, hairline-bordered, single-soft-drop treatment of Phil's hand-tuned `~/.config/swaync/style.css`, keeping structure, live `palette.sh` re-skin, and multi-color accents.

**Architecture:** All visuals come from one generated stylesheet in `sqlch_gui/ui/common.py` plus four Cairo `DrawingArea` widgets. This plan rewrites the stylesheet flat, de-Cairo's the two decorative shape widgets (`RibbonBanner`, `PennantTag`) into CSS-styled boxes, and repaints the three functional Cairo widgets (`TornSeparator`, `RecordBubble`, `VolumeMeter`) and the `NavColumn` glyph flat. `palette.py` gains fallback defaults for the newer palette keys the flat vocabulary uses.

**Tech Stack:** Python 3.11+, PyGObject / GTK 4 (4.22 locally), Cairo, GTK4 Layer Shell. Tests: stdlib `unittest` (run with `python3 -m unittest`), no pytest.

## Global Constraints

- **No hardcoded hex in the styling path.** Every color resolves from `palette.load()` (`~/.config/waybar/palette.sh`); literal hex appears only as the second arg to `colors.get(KEY, FALLBACK)`.
- **Preserve the live re-skin.** `window.py`'s `palette.sh` file-watch calls `load_custom_css()` on change; that path and behavior stay intact. `load_custom_css()` keeps its name and zero-arg signature.
- **No structural or layout changes.** Drawer mechanics, panel composition, the nav model, widget trees — all unchanged except the two call-site edits this plan names explicitly.
- **No TUI or CLI changes.** Only `sqlch_gui/` is touched.
- **Fonts:** `"JetBrains Mono", "Courier New", monospace` for all chrome; `"Inter", "system-ui", sans-serif` for `.meta-title` / `.meta-artist` only.
- **Radii:** 18 shell · 12 cards / plates / trays / info-panel · 7 buttons / chips / rows / entries · 6 `.small-badge`.
- **No `text-shadow` on any class. No `linear-gradient`. No per-element SVG texture** — a single faint fiber-noise (~0.06 alpha) on `.popup-window` only.
- **Accent discipline:** `ROOT` is the primary accent. `PIANO` (`.control-btn.primary` idle), `FORTE` (primary hover, `RecordBubble` armed, `.rec-badge`, VU hot/boost pips), `SEVENTH` (`.station-row.active`, `.station-live`) stay where they are used today, painted flat.
- Verify with `python3 -m unittest discover -s tests -v` (44 existing tests must stay green) plus the new `tests/test_gui_style.py`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `sqlch_gui/palette.py` | parse `palette.sh` → color dict, with fallbacks | add keys to `_DEFAULTS` |
| `sqlch_gui/ui/common.py` | generate + install the app stylesheet | split out `_build_css(colors)`, rewrite every rule flat |
| `sqlch_gui/ui/banner.py` | section headers, tag chips, drawer seam | `RibbonBanner` + `PennantTag` → `Gtk.Box`; `TornSeparator` flat repaint |
| `sqlch_gui/ui/controls.py` | VU meter, record button, nav rail | flat `_on_draw` for `RecordBubble` + `VolumeMeter`; `NavColumn` glyph color |
| `sqlch_gui/ui/eq_strip.py` | decorative bead strip | single-tone bead color that reads on the active row |
| `sqlch_gui/ui/station_list.py` | station library panel | drop the header wrapper box, add a filter guard |
| `sqlch_gui/ui/discover.py` | radio-browser panel | drop one `set_halign` call |
| `tests/test_gui_style.py` | **new** — smoke tests for the styling path | create |

---

## Task 1: Palette fallback defaults + test scaffold

**Files:**
- Modify: `sqlch_gui/palette.py:7-29` (the `_DEFAULTS` dict)
- Create: `tests/test_gui_style.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `palette._DEFAULTS` contains keys `DIM`, `LYRIC`, `STAFF_A_OUTER`, `STAFF_A_DROP`, `STAFF_A_HOVER`, `STAFF_A_INSET_TOP`, `STAFF_A_INSET_BOT`, `STAFF_A_BORDER`, `MEASURE`, `TEMPO`. `palette.load()` (unchanged signature) therefore always returns them even with no `palette.sh` present. `tests/test_gui_style.py` exists as the home for later tasks' smoke tests.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gui_style.py`:

```python
import unittest

from sqlch_gui import palette

# Keys the flat CSS vocabulary and Cairo widgets read via colors.get(...).
# They exist in the current-generation palette.sh; these must also be in
# _DEFAULTS so the no-palette fallback still resolves them.
_REQUIRED_KEYS = (
    "HALL", "STAGE", "WING", "DIM", "SCORE", "LYRIC", "REST",
    "ROOT", "SEVENTH", "PIANO", "FORTE", "SOTTO", "SHADOW", "STAFF",
    "STAFF_A_OUTER", "STAFF_A_DROP", "STAFF_A_INSET_BOT",
)


class TestPaletteDefaults(unittest.TestCase):
    def test_defaults_cover_flat_vocabulary(self):
        missing = [k for k in _REQUIRED_KEYS if k not in palette._DEFAULTS]
        self.assertEqual(missing, [], f"_DEFAULTS missing keys: {missing}")

    def test_load_without_file_still_resolves_keys(self):
        colors = palette.load("/nonexistent/palette.sh")
        for k in _REQUIRED_KEYS:
            self.assertIn(k, colors)
            self.assertTrue(colors[k], f"{k} resolved empty")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_gui_style -v`
Expected: `test_defaults_cover_flat_vocabulary` FAILs — `_DEFAULTS missing keys: ['DIM', 'LYRIC', 'STAFF_A_OUTER', 'STAFF_A_DROP', 'STAFF_A_INSET_BOT']`.

- [ ] **Step 3: Add the keys to `_DEFAULTS`**

In `sqlch_gui/palette.py`, the `_DEFAULTS` dict currently ends:

```python
    "GRAD_WING_HI": "#443f60",
    "GRAD_WING_LO": "#2d2944",
    "STAFF": "15,14,23",
}
```

Replace that tail with:

```python
    "GRAD_WING_HI": "#443f60",
    "GRAD_WING_LO": "#2d2944",
    "STAFF": "15,14,23",
    "DIM": "#1a1828",
    "LYRIC": "#c9c5da",
    "STAFF_A_OUTER": "0.50",
    "STAFF_A_DROP": "0.55",
    "STAFF_A_HOVER": "0.65",
    "STAFF_A_INSET_TOP": "0.08",
    "STAFF_A_INSET_BOT": "0.30",
    "STAFF_A_BORDER": "0.07",
    "MEASURE": "0 1px 2px rgba(0,0,0,0.80)",
    "TEMPO": "12px",
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_gui_style -v`
Expected: both tests PASS.

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS (46 total).

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/palette.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): add palette fallbacks for the flat style vocabulary

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WeRHAy7WJ9NYVC47TmTpAE"
```

---

## Task 2: Flat stylesheet (`common.py`)

**Files:**
- Modify: `sqlch_gui/ui/common.py` (full rewrite of the module body)
- Modify: `tests/test_gui_style.py` (append a test class)

**Interfaces:**
- Consumes: `palette._DEFAULTS` keys from Task 1; `palette.load()`.
- Produces:
  - `common._build_css(colors: dict) -> str` — pure function, builds the stylesheet text from a color dict. No side effects, no display needed.
  - `common.load_custom_css() -> None` — unchanged name/signature; now `_build_css(palette.load())` + install on the default display.
  - `common._hex_to_rgb(hex_val: str) -> str` — unchanged, still returns `"r, g, b"`.
  - New CSS class `.section-rule` (+ `.gold` modifier) consumed by Task 3. Removed classes: `.ribbon-label`, `.pennant-label`. All other existing class names are kept.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gui_style.py` (before the `if __name__` block):

```python
class TestFlatStylesheet(unittest.TestCase):
    def _all_color_dicts(self):
        return (palette.load(), dict(palette._DEFAULTS))

    def test_build_css_is_a_pure_function(self):
        from sqlch_gui.ui import common
        css = common._build_css(dict(palette._DEFAULTS))
        self.assertIsInstance(css, str)
        self.assertIn(".popup-window", css)
        self.assertIn(".section-rule", css)

    def test_no_paper_cutout_vocabulary(self):
        from sqlch_gui.ui import common
        css = common._build_css(palette.load())
        self.assertNotIn("linear-gradient", css)
        self.assertNotIn("text-shadow", css)
        # a single faint noise texture, on the shell only
        self.assertLessEqual(css.count("feTurbulence"), 1)

    def test_css_parses_without_error_on_every_palette(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui import common
        for colors in self._all_color_dicts():
            css = common._build_css(colors)
            errors = []
            prov = Gtk.CssProvider()
            prov.connect("parsing-error",
                         lambda p, sec, err: errors.append(err.message))
            prov.load_from_string(css)
            self.assertEqual(errors, [], f"CSS parse errors: {errors}")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_gui_style.TestFlatStylesheet -v`
Expected: FAIL — `AttributeError: module 'sqlch_gui.ui.common' has no attribute '_build_css'`.

- [ ] **Step 3: Rewrite `sqlch_gui/ui/common.py`**

Replace the **entire file** with:

```python
"""Shared UI styling: generates and installs the flat, swaync-style stylesheet."""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

_css_provider: Gtk.CssProvider | None = None


def _hex_to_rgb(hex_val: str) -> str:
    """Convert '#rrggbb' (or '#rgb') into a bare 'r, g, b' triple for rgba() strings."""
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r}, {g}, {b}"


def _build_css(colors: dict) -> str:
    """Build the app stylesheet from a palette color dict. Pure — no display,
    no side effects. Mirrors the vocabulary of ~/.config/swaync/style.css:
    flat fills, a hairline border, one soft drop; the hard-offset shadow and
    the faint fiber-noise live only on the outer .popup-window shell."""
    outline = colors.get('SHADOW', '#0f0e17')
    score = colors.get('SCORE', '#e0def4')
    score_rgb = _hex_to_rgb(score)
    staff = colors.get('STAFF', '15, 14, 23')

    stage = colors.get('STAGE', '#2a273f')
    wing = colors.get('WING', '#393552')
    dim = colors.get('DIM', '#1a1828')
    hall = colors.get('HALL', '#232136')
    lyric = colors.get('LYRIC', '#c9c5da')
    rest = colors.get('REST', '#908caa')
    root = colors.get('ROOT', '#c4a7e7')
    seventh = colors.get('SEVENTH', '#3e8fb0')
    piano = colors.get('PIANO', '#f6c177')
    forte = colors.get('FORTE', '#eb6f92')
    sotto = colors.get('SOTTO', '#ea9a97')

    a_outer = colors.get('STAFF_A_OUTER', '0.50')
    a_drop = colors.get('STAFF_A_DROP', '0.55')
    a_inset = colors.get('STAFF_A_INSET_BOT', '0.30')

    mono = '"JetBrains Mono", "Courier New", monospace'
    prop = '"Inter", "system-ui", sans-serif'

    hairline = f"1px solid rgba({score_rgb}, 0.14)"
    rule = f"1px solid rgba({score_rgb}, 0.13)"
    drop = f"0 1px 1px rgba({staff}, {a_drop})"
    recess = f"inset 0 1px 2px rgba({staff}, {a_inset})"
    press = f"inset 0 1px 3px rgba({staff}, 0.6)"
    shell_shadow = f"3px 4px 0 0 rgba({staff}, {a_drop})"

    shell_noise = (
        "url(\"data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='90' height='90'>"
        "<filter id='craft'>"
        "<feTurbulence type='fractalNoise' baseFrequency='0.55' numOctaves='3' result='n'/>"
        "<feColorMatrix type='matrix' values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.06 0' in='n' result='fiber'/>"
        "<feBlend mode='multiply' in='SourceGraphic' in2='fiber'/>"
        "</filter>"
        "<rect width='100%25' height='100%25' filter='url(%23craft)' fill='transparent'/>"
        "</svg>\")"
    )

    return f"""
    window {{
        background-color: transparent;
        font-family: {mono};
        font-size: 12px;
        color: {score};
    }}

    .popup-window {{
        background-color: {wing};
        background-image: {shell_noise};
        background-repeat: repeat;
        color: {score};
        font-family: {mono};
        border-radius: 18px;
        border: 1px solid rgba({score_rgb}, {a_outer});
        box-shadow: {shell_shadow};
        margin: 2px 10px 10px 2px;
        padding: 2px;
    }}

    .nav-row {{
        background-color: {stage};
        border-radius: 7px;
        padding: 3px 6px;
        border: {hairline};
        box-shadow: {drop};
    }}

    .nav-btn {{
        padding: 4px;
        margin: 2px 0;
        border-radius: 7px;
        color: {rest};
        background-color: {wing};
        background-image: none;
        border: {hairline};
        box-shadow: {drop};
    }}
    .nav-btn:hover {{
        background-color: {stage};
        color: {score};
    }}
    .nav-btn.active {{
        background-color: {root};
        color: {outline};
        font-weight: 700;
        box-shadow: {drop};
    }}

    .card {{
        background-color: {stage};
        border-radius: 12px;
        padding: 4px;
        border: {hairline};
        box-shadow: {drop};
        margin-bottom: 2px;
    }}

    .cover-art {{
        background-color: {wing};
        border-radius: 12px;
        border: {hairline};
        min-width: 220px;
        min-height: 220px;
        box-shadow: {drop};
    }}
    .cover-glyph {{
        font-size: 38px;
        font-weight: 700;
        color: {lyric};
    }}

    .corner-tag {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.6em;
        padding: 2px 6px;
        border-radius: 7px;
        border: {hairline};
        margin: 6px;
    }}
    .corner-tag-left {{
        background-color: {root};
        color: {outline};
    }}

    .list-plate {{
        background-color: {dim};
        border-radius: 12px;
        padding: 5px;
        border: {hairline};
        box-shadow: {recess};
    }}
    .list-plate row {{
        background: transparent;
    }}

    .list-header {{
        background-color: {stage};
        color: {score};
        font-family: {mono};
        font-weight: 700;
        border-radius: 7px;
        padding: 5px 8px;
        margin-bottom: 5px;
        border: {hairline};
        box-shadow: {drop};
    }}

    .station-row {{
        padding: 5px 7px;
        border-radius: 7px;
        margin-bottom: 3px;
        background-color: {stage};
        border: {hairline};
        box-shadow: {drop};
    }}
    .station-row:hover {{
        background-color: {wing};
    }}
    .station-row.active {{
        background-color: {seventh};
        color: {hall};
        border-color: {root};
    }}
    .station-row.active label {{
        color: {hall};
    }}
    .station-freq {{
        color: {lyric};
        font-weight: 700;
        font-family: {mono};
    }}
    .station-row.active .station-freq {{
        color: {hall};
    }}
    .station-live {{
        font-size: 0.8em;
        color: {seventh};
    }}
    .station-row.active .station-live {{
        color: {hall};
    }}

    .control-btn {{
        border-radius: 7px;
        min-width: 28px;
        min-height: 28px;
        padding: 0;
        background-color: {wing};
        background-image: none;
        color: {score};
        border: {hairline};
        box-shadow: {drop};
    }}
    .control-btn:hover {{
        background-color: {stage};
    }}
    .control-btn:active {{
        box-shadow: {press};
    }}
    .control-btn.primary {{
        min-width: 36px;
        min-height: 36px;
        border-radius: 9px;
        background-color: {piano};
        background-image: none;
        color: {hall};
    }}
    .control-btn.primary:hover {{
        background-color: {forte};
        color: {hall};
    }}

    .meta-title {{
        font-family: {prop};
        font-size: 1.05em;
        font-weight: 700;
        color: {score};
    }}
    .meta-artist {{
        font-family: {prop};
        font-size: 0.9em;
        color: {forte};
    }}
    .meta-genre {{
        font-family: {mono};
        font-size: 0.85em;
        color: {root};
    }}

    .thread-label {{
        font-family: {mono};
        font-size: 0.75em;
        color: rgba({score_rgb}, 0.28);
    }}
    .thread-label.lit {{
        color: {root};
        font-weight: 700;
    }}

    .tech-badge, .tag-chip {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.72em;
        background-color: {wing};
        color: {lyric};
        padding: 2px 7px;
        border-radius: 7px;
        border: {hairline};
    }}
    .tag-chip:hover {{
        background-color: {stage};
        color: {score};
    }}
    .tag-chip.country {{
        color: {sotto};
    }}
    .tech-badge.rec-badge {{
        background-color: {forte};
        color: {hall};
    }}

    .small-badge {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.65em;
        background-color: {dim};
        color: {root};
        padding: 2px 6px;
        border-radius: 6px;
    }}

    .section-rule {{
        border-top: {rule};
        margin: 20px 4px 8px;
        padding: 8px 2px 0;
    }}
    .section-rule label {{
        color: {lyric};
        font-family: {mono};
        font-weight: 700;
        font-size: 10px;
        letter-spacing: 0.14em;
    }}
    .section-rule.gold label {{
        color: {root};
    }}

    .pennant-btn {{
        background: transparent;
        border: none;
        box-shadow: none;
        padding: 0;
    }}
    .pennant-btn:hover {{
        background: transparent;
    }}

    .knob-tag {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.58em;
        color: {rest};
        letter-spacing: 0.05em;
    }}

    .brand-tag {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.56em;
        letter-spacing: 0.08em;
        color: rgba({score_rgb}, 0.35);
        margin: 6px 8px;
    }}

    popover.context-menu > contents {{
        background-color: {stage};
        background-image: none;
        color: {score};
        border-radius: 12px;
        border: {hairline};
        box-shadow: 0 4px 12px rgba({staff}, {a_drop});
        padding: 10px;
    }}
    popover.context-menu > arrow {{
        background-color: {stage};
        border: {hairline};
    }}
    .context-menu label {{
        color: {score};
        font-family: {mono};
        font-size: 0.85em;
        font-weight: 700;
        margin-top: 4px;
    }}
    .context-menu entry {{
        background-color: {dim};
        color: {score};
        border-radius: 7px;
        padding: 6px;
        border: {hairline};
        box-shadow: {recess};
    }}
    .context-menu entry:focus-within {{
        border: 1px solid {root};
    }}
    .context-menu separator {{
        background-color: rgba({score_rgb}, 0.13);
        min-height: 1px;
        margin: 6px 0;
    }}

    .menu-btn {{
        padding: 6px 8px;
        border-radius: 7px;
        color: {score};
        background-color: {wing};
        background-image: none;
        border: {hairline};
        box-shadow: {drop};
    }}
    .menu-btn:hover {{
        background-color: {stage};
    }}
    .menu-btn:active {{
        box-shadow: {press};
    }}
    .menu-btn.destructive-action {{
        color: {forte};
    }}
    .menu-btn.destructive-action:hover {{
        background-color: {forte};
        color: {hall};
    }}

    .field-entry {{
        background-color: {dim};
        background-image: none;
        color: {score};
        border-radius: 7px;
        padding: 5px 8px;
        border: {hairline};
        box-shadow: {recess};
    }}
    .field-entry:focus-within {{
        border: 1px solid {root};
    }}

    .search-btn {{
        border-radius: 7px;
        padding: 5px 10px;
        border: {hairline};
        box-shadow: {drop};
        background-image: none;
        background-color: {wing};
        color: {score};
        font-family: {mono};
        font-weight: 700;
    }}
    .search-btn:hover {{
        background-color: {stage};
    }}

    .info-panel {{
        background-color: {stage};
        border-radius: 12px;
        border: {hairline};
        box-shadow: {recess};
        padding: 8px;
    }}
    .info-panel.stale, .cover-art.stale {{
        opacity: 0.5;
    }}
    .info-line {{
        font-family: {mono};
        font-size: 0.72em;
        font-weight: 700;
        color: {lyric};
    }}
    """


def load_custom_css():
    global _css_provider
    css = _build_css(palette.load())

    display = Gdk.Display.get_default()
    if _css_provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _css_provider)
    _css_provider = Gtk.CssProvider()
    _css_provider.load_from_string(css)
    Gtk.StyleContext.add_provider_for_display(
        display,
        _css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_gui_style -v`
Expected: all `TestFlatStylesheet` tests PASS.

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Sanity-check the live install path**

Run:

```bash
python3 -c "
import gi; gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from sqlch_gui.ui import common
common.load_custom_css()
print('load_custom_css OK')
"
```

Expected: prints `load_custom_css OK` (a `Gtk-WARNING` about `Adwaita-dark/gtk.css` from the environment is pre-existing noise — ignore it). No `Theme parser error` mentioning `<data>` or a line/column in our CSS.

- [ ] **Step 6: Commit**

```bash
git add sqlch_gui/ui/common.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): flatten the stylesheet to the swaync vocabulary

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WeRHAy7WJ9NYVC47TmTpAE"
```

---

## Task 3: Section headers + tag chips + drawer seam (`banner.py`)

**Files:**
- Modify: `sqlch_gui/ui/banner.py` (full rewrite)
- Modify: `sqlch_gui/ui/station_list.py:117-126` (drop the header wrapper box), `sqlch_gui/ui/station_list.py:79-82` (add a filter guard)
- Modify: `sqlch_gui/ui/discover.py:38-40` (drop one `set_halign`)
- Modify: `tests/test_gui_style.py` (append a test class)

**Interfaces:**
- Consumes: `.section-rule` / `.section-rule.gold` and `.tag-chip` / `.tag-chip.country` CSS from Task 2.
- Produces:
  - `RibbonBanner(text: str, gold: bool = False)` — now a `Gtk.Box`; exposes `.label` (a `Gtk.Label`) and `.set_text(text: str)`. Renders as a hairline top-rule + engraved label.
  - `PennantTag(text: str, country: bool = False)` — now a `Gtk.Box`; exposes `.label` (a `Gtk.Label`). `isinstance(w, PennantTag)` and `w.label.get_text()` both still work (relied on by `station_list.filter_station_rows`).
  - `TornSeparator(orientation=Gtk.Orientation.HORIZONTAL)` — unchanged API (`.set_grabbed(bool)`, `_THICKNESS`); repainted as a recessed hairline groove + short grab bar.
  - `banner._hex_to_rgb_floats` retained. `RibbonBanner.TAIL_H`, `PennantTag.NOTCH`, `banner._shade`, `banner._lighten` removed.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gui_style.py`:

```python
class TestBannerWidgets(unittest.TestCase):
    def test_ribbon_banner_is_a_box_with_engraved_label(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.banner import RibbonBanner
        b = RibbonBanner("jazz")
        self.assertIsInstance(b, Gtk.Box)
        self.assertTrue(b.has_css_class("section-rule"))
        self.assertEqual(b.label.get_text(), "JAZZ")
        b.set_text("news")
        self.assertEqual(b.label.get_text(), "NEWS")
        g = RibbonBanner("browse categories", gold=True)
        self.assertTrue(g.has_css_class("gold"))

    def test_pennant_tag_is_a_box_exposing_label(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.banner import PennantTag
        p = PennantTag("US", country=True)
        self.assertIsInstance(p, Gtk.Box)
        self.assertTrue(p.has_css_class("tag-chip"))
        self.assertTrue(p.has_css_class("country"))
        self.assertEqual(p.label.get_text(), "US")

    def test_torn_separator_draw_does_not_raise(self):
        import cairo
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.banner import TornSeparator
        for orient in (Gtk.Orientation.VERTICAL, Gtk.Orientation.HORIZONTAL):
            sep = TornSeparator(orient)
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 18, 200)
            cr = cairo.Context(surf)
            sep._on_draw(sep, cr, 18, 200)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_gui_style.TestBannerWidgets -v`
Expected: FAIL — `test_ribbon_banner_is_a_box_with_engraved_label` errors because `RibbonBanner` is a `Gtk.Overlay`, not a `Gtk.Box`.

- [ ] **Step 3: Rewrite `sqlch_gui/ui/banner.py`**

Replace the **entire file** with:

```python
"""Section-rule headers, flat tag chips, and the drawer seam.

RibbonBanner and PennantTag were Cairo-drawn papercraft shapes (torn
ribbon tails, a cut-flag notch); they are now plain CSS-styled boxes.
TornSeparator still draws the drawer seam, but as a recessed hairline
groove with a short grab bar rather than a ragged tear.
"""

import cairo
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from .. import palette


def _hex_to_rgb_floats(hex_val: str) -> tuple[float, float, float]:
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


class RibbonBanner(Gtk.Box):
    """Section header: a hairline top-rule with a small engraved label,
    left-set. The rule IS the break -- no box frame around the group."""

    def __init__(self, text: str, gold: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_hexpand(True)
        self.add_css_class("section-rule")
        if gold:
            self.add_css_class("gold")
        self.label = Gtk.Label(label=text.upper(), xalign=0.0)
        self.label.set_hexpand(True)
        self.append(self.label)

    def set_text(self, text: str):
        self.label.set_text(text.upper())


class PennantTag(Gtk.Box):
    """Flat tag chip (was a Cairo cut-flag pennant). `.label` is kept as a
    real child so station_list's filter can read its text."""

    def __init__(self, text: str, country: bool = False):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("tag-chip")
        if country:
            self.add_css_class("country")
        self.label = Gtk.Label(label=text)
        self.append(self.label)


class TornSeparator(Gtk.DrawingArea):
    """Drawer seam between the Now Playing sheet and the drawer: a recessed
    hairline groove with a short centered grab bar.

    Purely visual -- the window owns the drag gesture and drawer state;
    this widget just draws the seam and swaps the grab/grabbing cursor.
    VERTICAL is a strip beside Now Playing (side drawer); HORIZONTAL a
    strip below it (drop drawer) -- same construction, axes swapped.
    """

    _THICKNESS = 18
    _GRAB = 23.0

    def __init__(self, orientation: Gtk.Orientation = Gtk.Orientation.HORIZONTAL):
        super().__init__()
        self._orientation = orientation
        if orientation == Gtk.Orientation.VERTICAL:
            self.set_vexpand(True)
            self.set_content_width(self._THICKNESS)
        else:
            self.set_hexpand(True)
            self.set_content_height(self._THICKNESS)
        self.set_draw_func(self._on_draw)
        self.set_cursor_from_name("grab")
        self.set_tooltip_text("Drag to open the drawer")

    def set_grabbed(self, grabbed: bool):
        self.set_cursor_from_name("grabbing" if grabbed else "grab")

    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        stage = _hex_to_rgb_floats(colors.get('STAGE', '#2a273f'))
        score = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        lyric = _hex_to_rgb_floats(colors.get('LYRIC', '#c9c5da'))
        vertical = self._orientation == Gtk.Orientation.VERTICAL

        cr.set_source_rgba(*stage, 1.0)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Faint full-length hairline down the seam's centerline.
        cr.set_line_width(1.0)
        cr.set_source_rgba(*score, 0.15)
        if vertical:
            x = round(width / 2.0) + 0.5
            cr.move_to(x, 4.0)
            cr.line_to(x, height - 4.0)
        else:
            y = round(height / 2.0) + 0.5
            cr.move_to(4.0, y)
            cr.line_to(width - 4.0, y)
        cr.stroke()

        # Short, more-opaque grab bar at the center.
        cr.set_line_width(2.0)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(*lyric, 0.55)
        if vertical:
            cx = width / 2.0
            cr.move_to(cx, height / 2.0 - self._GRAB)
            cr.line_to(cx, height / 2.0 + self._GRAB)
        else:
            cy = height / 2.0
            cr.move_to(width / 2.0 - self._GRAB, cy)
            cr.line_to(width / 2.0 + self._GRAB, cy)
        cr.stroke()
```

- [ ] **Step 4: Update `station_list.py` call sites**

In `sqlch_gui/ui/station_list.py`, `filter_station_rows` currently opens:

```python
        child = row.get_child()
        # Let explicit structural heading text rows through without suppression
        if not isinstance(child, Gtk.Box):
            return True
```

Insert the header guard so section rules never match the filter (headers stay hidden while filtering, as they were):

```python
        child = row.get_child()
        # Section-rule headers never participate in filtering.
        if isinstance(child, RibbonBanner):
            return False
        # Let explicit structural heading text rows through without suppression
        if not isinstance(child, Gtk.Box):
            return True
```

Then in `refresh()`, replace the header wrapper block:

```python
        for g_name in sorted(groups.keys()):
            # Category Header Separator
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            header_box.set_margin_top(8)
            header_box.set_margin_bottom(4)

            ribbon = RibbonBanner(g_name)
            ribbon.set_halign(Gtk.Align.START)
            header_box.append(ribbon)
            self.list_box.append(header_box)
```

with:

```python
        for g_name in sorted(groups.keys()):
            # Category header: a hairline section rule spanning the list.
            self.list_box.append(RibbonBanner(g_name))
```

- [ ] **Step 5: Update `discover.py` call site**

In `sqlch_gui/ui/discover.py`, replace:

```python
        self.browse_title = RibbonBanner("Browse Categories", gold=True)
        self.browse_title.set_halign(Gtk.Align.START)
        self.discovery_container.append(self.browse_title)
```

with:

```python
        self.browse_title = RibbonBanner("Browse Categories", gold=True)
        self.discovery_container.append(self.browse_title)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_gui_style.TestBannerWidgets -v`
Expected: all PASS.

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

Import-sanity for the touched panels:

```bash
python3 -c "
import gi; gi.require_version('Gtk','4.0'); gi.require_version('Gtk4LayerShell','1.0')
from gi.repository import Gtk
import sqlch_gui.ui.station_list, sqlch_gui.ui.discover, sqlch_gui.ui.window
print('panel imports OK')
"
```

Expected: prints `panel imports OK`.

- [ ] **Step 7: Commit**

```bash
git add sqlch_gui/ui/banner.py sqlch_gui/ui/station_list.py sqlch_gui/ui/discover.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): section-rule headers, flat chips, recessed drawer seam

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WeRHAy7WJ9NYVC47TmTpAE"
```

---

## Task 4: Flatten the functional Cairo widgets (`controls.py`)

**Files:**
- Modify: `sqlch_gui/ui/controls.py` — `RecordBubble._on_draw` (rewrite), `VolumeMeter._on_draw` (rewrite), `NavColumn._draw_display` (one line + comment)
- Modify: `tests/test_gui_style.py` (append a test class)

**Interfaces:**
- Consumes: nothing new — reads `palette.load()` keys directly.
- Produces: no signature changes. `RecordBubble`, `VolumeMeter`, `NavColumn` keep every public method, signal, and constructor. Only pixels change: flat fills, hairline rings, a recessed VU trough, no radial gradients, no hardcoded RGB literals.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gui_style.py`:

```python
class TestControlWidgetsFlat(unittest.TestCase):
    def _ctx(self, w, h):
        import cairo
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        return cairo.Context(surf)

    def test_record_bubble_draw_flat_no_raise(self):
        from sqlch_gui.ui.controls import RecordBubble
        b = RecordBubble()
        b._on_draw(b, self._ctx(34, 34), 34, 34)
        b.set_state(True, "track")
        b._on_draw(b, self._ctx(34, 34), 34, 34)

    def test_volume_meter_draw_flat_no_raise(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        from sqlch_gui.ui.controls import VolumeMeter
        adj = Gtk.Adjustment(value=0.6, lower=0.0, upper=1.0, step_increment=0.05)
        m = VolumeMeter(adj)
        m._on_draw(m, self._ctx(160, 18), 160, 18)
        m.boosted = True
        m._on_draw(m, self._ctx(160, 18), 160, 18)

    def test_controls_source_has_no_hardcoded_rgb_literals(self):
        import pathlib
        src = pathlib.Path("sqlch_gui/ui/controls.py").read_text()
        # the pop-it bubble's hardcoded reds / greys are gone
        self.assertNotIn("0.86, 0.20, 0.18", src)
        self.assertNotIn("cairo.RadialGradient", src)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_gui_style.TestControlWidgetsFlat -v`
Expected: `test_controls_source_has_no_hardcoded_rgb_literals` FAILs (`cairo.RadialGradient` still present).

- [ ] **Step 3: Rewrite `RecordBubble._on_draw`**

In `sqlch_gui/ui/controls.py`, replace the whole `RecordBubble._on_draw` method (from `def _on_draw` through the end of the class) with:

```python
    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        if self.recording:
            face = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))
            glyph = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        else:
            face = _hex_to_rgb_floats(colors.get('WING', '#393552'))
            glyph = _hex_to_rgb_floats(colors.get('LYRIC', '#c9c5da'))
        ring = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))

        cx, cy = width / 2.0, height / 2.0
        radius = min(width, height) / 2.0 - 3.0

        # Flat disc + hairline ring, same vocabulary as the CSS .control-btn.
        cr.set_source_rgba(*face, 1.0)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()

        cr.set_line_width(1.0)
        cr.set_source_rgba(*ring, 0.15)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Centered record glyph: a small filled square.
        s = radius * 0.5
        cr.set_source_rgba(*glyph, 1.0)
        cr.rectangle(cx - s / 2.0, cy - s / 2.0, s, s)
        cr.fill()
```

- [ ] **Step 4: Rewrite `VolumeMeter._on_draw`**

Replace the whole `VolumeMeter._on_draw` method with:

```python
    def _on_draw(self, area, cr, width, height, user_data=None):
        colors = palette.load()
        trough = _hex_to_rgb_floats(colors.get('DIM', '#1a1828'))
        score = _hex_to_rgb_floats(colors.get('SCORE', '#e0def4'))
        low_rgb = _hex_to_rgb_floats(colors.get('SEVENTH', '#79a383'))
        hot_rgb = _hex_to_rgb_floats(colors.get('FORTE', '#eb6f92'))

        norm = self._norm()
        filled = round(norm * self.N_SEGMENTS)
        rects = self._segment_rects(width, height)

        # Recessed trough behind the whole pip strip (matches the CSS
        # slider-trough idiom -- DIM well, pips sit proud of it).
        cr.set_source_rgba(*trough, 1.0)
        self._rounded_bar(cr, 0.0, 1.0, width, max(0.0, height - 2.0))
        cr.fill()

        for i, (x, y, w, h) in enumerate(rects):
            t = i / (self.N_SEGMENTS - 1)
            r = low_rgb[0] + (hot_rgb[0] - low_rgb[0]) * t
            g = low_rgb[1] + (hot_rgb[1] - low_rgb[1]) * t
            b = low_rgb[2] + (hot_rgb[2] - low_rgb[2]) * t
            if i < filled:
                cr.set_source_rgba(r, g, b, 1.0)
            else:
                cr.set_source_rgba(*score, 0.12)
            self._rounded_bar(cr, x, y + 2.0, w, h - 4.0)
            cr.fill()

        if self.boosted:
            last_x = rects[-1][0] + rects[-1][2]
            overflow_w = width - self._MARGIN - last_x - self._GAP
            if overflow_w > 0:
                cr.set_source_rgba(*hot_rgb, 1.0)
                self._rounded_bar(cr, last_x + self._GAP, 2.0, overflow_w, height - 4.0)
                cr.fill()
```

- [ ] **Step 5: Recolor the `NavColumn` monitor glyph**

In `NavColumn._draw_display`, replace:

```python
        mini_active = self.active == "mini"
        # Matches .nav-btn.active's `color: {outline}` (palette SHADOW) when
        # Now Playing is selected, .nav-btn's plain `color: {REST}` otherwise --
        # Cairo draws don't pick up GTK CSS `color`, so it's read explicitly.
        rgb = _hex_to_rgb_floats(colors.get('SHADOW' if mini_active else 'REST', '#4e4e52'))
```

with:

```python
        mini_active = self.active == "mini"
        # Matches the new .nav-btn foreground: SCORE when Now Playing is the
        # active view, plain REST otherwise. Cairo draws don't pick up GTK
        # CSS `color`, so it's read from the palette explicitly.
        rgb = _hex_to_rgb_floats(colors.get('SCORE' if mini_active else 'REST', '#e0def4'))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_gui_style.TestControlWidgetsFlat -v`
Expected: all PASS.

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add sqlch_gui/ui/controls.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): flatten RecordBubble, VolumeMeter, and the nav glyph

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WeRHAy7WJ9NYVC47TmTpAE"
```

---

## Task 5: EqStrip bead color + full visual verification

**Files:**
- Modify: `sqlch_gui/ui/eq_strip.py` — `EqStrip._on_draw` (single-tone bead color)
- Modify: `tests/test_gui_style.py` (append a test)

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature change. `EqStrip` beads render in one palette tone (`HALL`) that reads against the flat `.station-row.active` (`SEVENTH`) fill they sit on, instead of the old `ROOT`→`SEVENTH` ramp that would vanish into a flat `SEVENTH` row.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gui_style.py`:

```python
class TestEqStrip(unittest.TestCase):
    def test_bead_draw_no_raise_and_single_tone(self):
        import cairo, pathlib
        from sqlch_gui.ui.eq_strip import EqStrip
        s = EqStrip(n_beads=3, width=18, height=11)
        s._running = True
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 18, 11)
        s._on_draw(s, cairo.Context(surf), 18, 11)
        src = pathlib.Path("sqlch_gui/ui/eq_strip.py").read_text()
        # the ROOT->SEVENTH cross-fade is gone
        self.assertNotIn("tail_r", src)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_gui_style.TestEqStrip -v`
Expected: FAIL — `tail_r` still present in `eq_strip.py`.

- [ ] **Step 3: Rewrite `EqStrip._on_draw`**

In `sqlch_gui/ui/eq_strip.py`, replace the whole `_on_draw` method with:

```python
    def _on_draw(self, area, cr, width, height, user_data=None):
        # One flat tone that reads against the .station-row.active fill
        # (SEVENTH) these beads sit on -- HALL is that row's own text color.
        colors = palette.load()
        r, g, b = _hex_to_rgb_floats(colors.get('HALL', '#232136'))

        n = self.n_beads
        gap = 3.0
        bead_w = (width - gap * (n - 1)) / n

        for i in range(n):
            if self._running:
                level = 0.35 + 0.65 * abs(math.sin(self._phase + i * 0.8))
            else:
                level = 0.12
            bead_h = max(3.0, height * level)
            x = i * (bead_w + gap)
            y = height - bead_h
            cr.set_source_rgba(r, g, b, 0.85)
            self._rounded_bar(cr, x, y, bead_w, bead_h)
            cr.fill()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS (existing 44 + all new `test_gui_style` classes).

- [ ] **Step 5: Commit**

```bash
git add sqlch_gui/ui/eq_strip.py tests/test_gui_style.py
git commit -m "feat(sqlch-gui): single-tone EqStrip beads that read on the flat active row

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WeRHAy7WJ9NYVC47TmTpAE"
```

- [ ] **Step 6: Live visual verification**

Launch the working tree on the live session (see the `sqlch-gui-dev-launch` memory for the full rationale):

1. Read the installed wrapper for current env: `head -40 /etc/profiles/per-user/prepko/bin/sqlch-gui` — note `LD_PRELOAD` (the `libgtk4-layer-shell.so` path) and the `PYTHONPATH` it sets.
2. In a **separate** command first: `pkill -f "python3 -m sqlch_gui"` (running it inside the launch script kills the launcher's own shell).
3. Launch with `/home/prepko/sqlch` **first** on `PYTHONPATH`, the wrapper's other env preserved, `LD_PRELOAD` set. Run in the background.
4. Confirm a clean start in the task log: no `layer-shell` "linked after libwayland" warnings. `VK_SUBOPTIMAL` / `Gdk` vk warnings are benign.

Then ask Phil to screenshot, across **two palettes** (a dark one and a lighter one — switch via his theme switcher, which rewrites `palette.sh` and should trigger the live re-skin):
- Now Playing (idle + playing)
- the Library drawer open (grouped list, a section rule, an active row with the mini Eq strip, a right-click context menu)
- Discover (search bar, the "Browse Categories" gold rule, genre chips, a results row with a country chip + bitrate badge)

Check for: any element still carrying a gradient / texture / drop-offset / letterpress; unreadable text on the active row or chips; the section rules spanning full width; the drawer seam reading as a groove; the frame showing a single clean hard-offset.

5. Kill the dev instance by PID in a **separate** command once Phil has seen it. Do not leave it running.

- [ ] **Step 7: Apply any visual fixes Phil calls out**

Likely candidates (only if raised): trim the `.section-rule` top margin for the first group in a list; nudge `.station-row.active` contrast (swap `SEVENTH`→another tone) if a palette makes it unreadable; `now_playing.py` / `station_list.py` inter-element margins now that boxed frames are gone. Make the change, re-run `python3 -m unittest discover -s tests -v`, commit with a `style(sqlch-gui):` message.

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| Palette mapping table (STAGE/WING/DIM/SCORE/LYRIC/REST/ROOT + STAFF alphas) | Task 2 `_build_css` locals |
| `palette.py` `_DEFAULTS` additions | Task 1 |
| Retained multi-color accents (SEVENTH / PIANO / FORTE) | Task 2 (`.station-row.active`, `.station-live`, `.control-btn.primary`, `.rec-badge`), Task 4 (VU pips, RecordBubble armed) |
| Shared vocabulary (`hairline`/`drop`/`recess`/`press`, radii 18/12/7, no text-shadow, fonts) | Task 2 |
| Window frame (single `3px 4px 0 0`, faint shell-only noise, 18px) | Task 2 `.popup-window` + `shell_noise` |
| Section headers → rule + label; API unchanged; call sites | Task 3 |
| `TornSeparator` → recessed groove + grab bar | Task 3 |
| `PennantTag` → plain chip; `isinstance` + `.label` preserved | Task 3 |
| `RecordBubble` → flat disc + hairline ring + glyph; signals/state intact | Task 4 |
| `VolumeMeter` → flat pips on a DIM recessed trough | Task 4 |
| `NavColumn` glyph → SCORE/REST | Task 4 |
| `EqStrip` bead recheck | Task 5 |
| `.cover-art` loses matted rings; `.cover-glyph`/`.corner-tag` lose `rotate()` | Task 2 (rotate/inset-rings simply absent from the new rules) |
| Element-level flattening sweep (all `.nav-btn`/`.card`/`.menu-btn`/… ) | Task 2 |
| Live `palette.sh` re-skin preserved | Task 2 (`load_custom_css` keeps name/signature; `window.py` untouched) |
| Verification: smoke test + live dev instance across palettes | Tasks 1–5 smoke tests; Task 5 steps 6–7 |
| Out of scope: no layout/feature/TUI/CLI changes | honored — only the two named call-site edits touch panels |

No gaps.

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases"/"similar to Task N". Every code step is a full literal block. Task 5 step 7 lists *conditional* follow-up fixes with concrete candidates, gated on Phil's feedback — not a placeholder for required work.

**3. Type consistency:**
- `_build_css(colors: dict) -> str` defined in Task 2, referenced by Task 2's tests only. `load_custom_css()` name/signature unchanged everywhere.
- `RibbonBanner` / `PennantTag` are `Gtk.Box` with a `.label: Gtk.Label` attribute and (RibbonBanner) `.set_text(str)` — consumed by `station_list.filter_station_rows` (`isinstance` + `w.label.get_text()`) and the Task 3 tests, consistent.
- `TornSeparator` keeps `_THICKNESS`, `.set_grabbed(bool)`, `_on_draw(area, cr, width, height, user_data=None)` — `window.py` uses `TornSeparator(orientation=…)`, `.set_grabbed()`, and attaches a drag gesture; all intact.
- `RecordBubble._on_draw` / `VolumeMeter._on_draw` / `EqStrip._on_draw` keep the `(self, area, cr, width, height, user_data=None)` signature the tests and `set_draw_func` rely on.
- `_hex_to_rgb_floats` retained in `banner.py`, `controls.py`, `eq_strip.py` (each module has its own copy today — unchanged).

Consistent.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-02-swaync-flat-restyle.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
