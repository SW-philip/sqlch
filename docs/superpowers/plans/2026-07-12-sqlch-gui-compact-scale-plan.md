# Compact Player + Library/Discover Scale-Down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink `sqlch_gui`'s whole popup — Now Playing card, Library rows, and Discover panel — to roughly 75% of current scale (sizing/spacing/fonts only, no layout restructuring), plus give the previously-unstyled search/filter/add-station entries the same dashed-fabric look as the rest of the UI.

**Architecture:** Eleven small, mostly-independent tasks grouped by file. Tasks 2-6 all edit `common.py`'s CSS (each touching a disjoint set of rules, so ordering between them doesn't matter). Tasks 7-8 edit `controls.py`. Task 9 touches `eq_strip.py` plus one call site in `station_list.py`. Task 10 is `now_playing.py`'s sizing/spacing. Task 11 is `station_list.py`/`discover.py`'s remaining margins/spacing (distinct lines from Task 9's edit in the same file). Task 12 is a manual full-pass QA checklist with no code changes, covering the spec's Testing section end to end.

**Tech Stack:** Python 3.12, GTK4 + Gtk4LayerShell (PyGObject), Cairo for custom-drawn widgets (`controls.py`, `eq_strip.py`, `banner.py`). No test framework in this repo (consistent with prior plans, e.g. `docs/plans/2026-07-04-sqlch-gui-now-playing-lbp-plan.md`): pure-syntax changes are verified with `python3 -c "import ast; ast.parse(...)"`; all visual changes are verified by running the app.

**Dev launch note (for the manual-verify steps):** Running `python -m sqlch_gui` directly won't get Wayland layer-shell positioning right. Instead, copy the env exports from the installed wrapper (`head -30 /etc/profiles/per-user/prepko/bin/sqlch-gui`) — especially `LD_PRELOAD` of `libgtk4-layer-shell.so` — but put `/home/prepko/sqlch` **first** in `PYTHONPATH` so the working tree wins over the nix-store copy the wrapper prepends. Kill any previously running dev instance with `pkill -f "python3 -m sqlch_gui"` in a **separate** command first (running it inside the same launch script kills its own wrapper shell). Always kill the dev instance (by PID) once you've confirmed a step, rather than leaving it running.

**Spec:** `docs/superpowers/specs/2026-07-11-sqlch-gui-compact-scale-design.md`

---

## Task 1: Window footprint

**Files:**
- Modify: `sqlch_gui/ui/window.py:16-32`

- [ ] **Step 1: Shrink the drawer's max-height ceiling**

In `sqlch_gui/ui/window.py`, replace:

```python
MAX_DRAWER_HEIGHT = 420        # ceiling; the effective max also fits the monitor
DRAWER_BOTTOM_GAP = 12         # breathing room kept above the screen's bottom edge
```

with:

```python
MAX_DRAWER_HEIGHT = 320        # ceiling; the effective max also fits the monitor
DRAWER_BOTTOM_GAP = 12         # breathing room kept above the screen's bottom edge
```

- [ ] **Step 2: Shrink the default window width**

Replace:

```python
        self.set_title("sqlch-gui")
        # Now Playing is permanently visible; Library/Discover live in a
        # drawer beneath the torn seam. Height is content-driven so the
        # layer-shell surface hugs the card when closed and grows as the
        # drawer is pulled open.
        self.set_default_size(380, -1)
```

with:

```python
        self.set_title("sqlch-gui")
        # Now Playing is permanently visible; Library/Discover live in a
        # drawer beneath the torn seam. Height is content-driven so the
        # layer-shell surface hugs the card when closed and grows as the
        # drawer is pulled open.
        self.set_default_size(290, -1)
```

- [ ] **Step 3: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/window.py').read())"
```

Expected: no output

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/window.py
git commit -m "feat(sqlch-gui): shrink window default width and drawer max-height"
```

---

## Task 2: Core card & cover-art CSS

**Files:**
- Modify: `sqlch_gui/ui/common.py` (`.popup-window`, `.sidebar`, `.nav-btn`, `.card`, `.cover-art`, `.cover-glyph`)

- [ ] **Step 1: Tighten `.popup-window`**

In `sqlch_gui/ui/common.py`, replace:

```python
    .popup-window {{
        background-color: {bg_color};
        background-image: {svg_tactile_filter}, linear-gradient(165deg, {colors.get('GRAD_HALL_HI', '#e6dfce')}, {bg_color});
        background-repeat: repeat, no-repeat;
        color: {score};
        border-radius: 16px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 3px {outline}, 6px 6px 0 3px {outline}, 10px 10px 0 3px {shadow}, {hem(8)};
        margin: 3px 14px 14px 3px;
        padding: 3px;
    }}
```

with:

```python
    .popup-window {{
        background-color: {bg_color};
        background-image: {svg_tactile_filter}, linear-gradient(165deg, {colors.get('GRAD_HALL_HI', '#e6dfce')}, {bg_color});
        background-repeat: repeat, no-repeat;
        color: {score};
        border-radius: 13px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 3px {outline}, 6px 6px 0 3px {outline}, 10px 10px 0 3px {shadow}, {hem(8)};
        margin: 2px 10px 10px 2px;
        padding: 2px;
    }}
```

- [ ] **Step 2: Tighten `.sidebar` and `.nav-btn`**

Replace:

```python
    .sidebar {{
        background-color: {colors.get('GRAD_STAGE_LO', '#b04343')};
        background-image: {svg_tactile_filter}, linear-gradient(130deg, {colors.get('GRAD_STAGE_HI', '#d35f5f')}, {colors.get('GRAD_STAGE_LO', '#b04343')});
        background-repeat: repeat, no-repeat;
        border-radius: 12px;
        padding: 5px 3px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 2px transparent, {slight}, {hem(5)};
    }}

    .nav-btn {{
        padding: 6px;
        margin: 3px 0px;
        border-radius: 8px;
        color: {colors.get('REST', '#4e4e52')};
        background: transparent;
        border: 2px dashed transparent;
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
```

with:

```python
    .sidebar {{
        background-color: {colors.get('GRAD_STAGE_LO', '#b04343')};
        background-image: {svg_tactile_filter}, linear-gradient(130deg, {colors.get('GRAD_STAGE_HI', '#d35f5f')}, {colors.get('GRAD_STAGE_LO', '#b04343')});
        background-repeat: repeat, no-repeat;
        border-radius: 10px;
        padding: 4px 2px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 2px transparent, {slight}, {hem(5)};
    }}

    .nav-btn {{
        padding: 4px;
        margin: 2px 0px;
        border-radius: 6px;
        color: {colors.get('REST', '#4e4e52')};
        background: transparent;
        border: 2px dashed transparent;
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
```

- [ ] **Step 3: Tighten `.card`**

Replace:

```python
    .card {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 12px;
        padding: 6px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(6)};
        margin-bottom: 2px;
    }}
```

with:

```python
    .card {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 10px;
        padding: 4px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(6)};
        margin-bottom: 2px;
    }}
```

- [ ] **Step 4: Shrink `.cover-art` and `.cover-glyph`**

Replace:

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 12px;
        min-width: 130px;
        min-height: 130px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(5)};
    }}
    .cover-glyph {{
        font-size: 50px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}
```

with:

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        min-width: 98px;
        min-height: 98px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(5)};
    }}
    .cover-glyph {{
        font-size: 38px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}
```

- [ ] **Step 5: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "feat(sqlch-gui): shrink popup frame, sidebar, card, and cover-art CSS"
```

---

## Task 3: Library/list CSS

**Files:**
- Modify: `sqlch_gui/ui/common.py` (`.list-plate`, `.list-header`, `.station-row`)

- [ ] **Step 1: Tighten `.list-plate`, `.list-header`, `.station-row`**

Replace:

```python
    .list-plate {{
        background-color: {colors.get('HALL', '#fdf8ee')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 14px;
        padding: 6px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(4)};
    }}
    .list-plate row {{
        background: transparent;
    }}

    .list-header {{
        background-color: {colors.get('WING', '#eaddca')};
        color: {score};
        font-weight: bold;
        border-radius: 10px;
        padding: 6px 10px;
        margin-bottom: 6px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(4)};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.40), 0 1px 1px rgba({staff},0.5);
    }}

    .station-row {{
        padding: 5px 8px;
        border-radius: 10px;
        margin-bottom: 2px;
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(3, puff=False)};
    }}
```

with:

```python
    .list-plate {{
        background-color: {colors.get('HALL', '#fdf8ee')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 12px;
        padding: 5px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(4)};
    }}
    .list-plate row {{
        background: transparent;
    }}

    .list-header {{
        background-color: {colors.get('WING', '#eaddca')};
        color: {score};
        font-weight: bold;
        border-radius: 8px;
        padding: 5px 8px;
        margin-bottom: 5px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(4)};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.40), 0 1px 1px rgba({staff},0.5);
    }}

    .station-row {{
        padding: 4px 6px;
        border-radius: 8px;
        margin-bottom: 2px;
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(3, puff=False)};
    }}
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "feat(sqlch-gui): tighten library list-plate/header/row CSS"
```

---

## Task 4: Control buttons + corner-tag CSS

**Files:**
- Modify: `sqlch_gui/ui/common.py` (`.control-btn`, `.control-btn.primary`, `.corner-tag`)

- [ ] **Step 1: Shrink `.control-btn`**

Replace:

```python
    .control-btn {{
        border-radius: 14px;
        min-width: 38px;
        min-height: 38px;
        padding: 0;
        background-color: {colors.get('WING', '#f2ece1')};
        color: {score};
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(4)};
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
```

with:

```python
    .control-btn {{
        border-radius: 11px;
        min-width: 28px;
        min-height: 28px;
        padding: 0;
        background-color: {colors.get('WING', '#f2ece1')};
        color: {score};
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight}, {hem(4)};
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
```

- [ ] **Step 2: Shrink `.control-btn.primary`**

Replace:

```python
    .control-btn.primary {{
        min-width: 48px;
        min-height: 48px;
        border-radius: 17px;
        background-color: {colors.get('PIANO', '#2c2c30')};
        color: {colors.get('HALL', '#fdf8ee')};
        border: 2px dashed {thread_light};
        box-shadow: 0 0 0 2px {outline}, {slight}, {hem(4)};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.30), 0 1px 2px rgba({staff}, 0.70);
    }}
```

with:

```python
    .control-btn.primary {{
        min-width: 36px;
        min-height: 36px;
        border-radius: 13px;
        background-color: {colors.get('PIANO', '#2c2c30')};
        color: {colors.get('HALL', '#fdf8ee')};
        border: 2px dashed {thread_light};
        box-shadow: 0 0 0 2px {outline}, {slight}, {hem(4)};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.30), 0 1px 2px rgba({staff}, 0.70);
    }}
```

- [ ] **Step 3: Shrink `.corner-tag`**

Replace:

```python
    .corner-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.65em;
        padding: 2px 7px;
        border-radius: 8px;
        box-shadow: 0 2px 0 rgba({staff}, 0.4);
        margin: 5px;
    }}
```

with:

```python
    .corner-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.6em;
        padding: 2px 5px;
        border-radius: 8px;
        box-shadow: 0 2px 0 rgba({staff}, 0.4);
        margin: 5px;
    }}
```

- [ ] **Step 4: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "feat(sqlch-gui): shrink control buttons and corner-tag CSS"
```

---

## Task 5: Typography CSS

**Files:**
- Modify: `sqlch_gui/ui/common.py` (`.meta-title`, `.meta-artist`, `.thread-label`, `.tech-badge`/`.tag-chip`, `.small-badge`, `.ribbon-label`, `.pennant-label`, `.knob-tag`, `.brand-tag`)

- [ ] **Step 1: Step down `.meta-title` / `.meta-artist`**

Replace:

```python
    .meta-title {{
        font-family: "Fredoka", "Baloo 2", "Chalkboard SE", sans-serif;
        font-size: 1.25em;
        font-weight: 900;
        color: {score};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.45), 0 1px 1px rgba({staff},0.6), 1px 3px 0 {outline};
    }}
    .meta-artist {{
        font-family: "Fredoka", sans-serif;
        font-size: 1.0em;
        color: {colors.get('FORTE', '#8c3b3b')};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.35), 0 1px 1px rgba({staff},0.4), 1px 2px 0 {outline};
    }}
```

with:

```python
    .meta-title {{
        font-family: "Fredoka", "Baloo 2", "Chalkboard SE", sans-serif;
        font-size: 1.05em;
        font-weight: 900;
        color: {score};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.45), 0 1px 1px rgba({staff},0.6), 1px 3px 0 {outline};
    }}
    .meta-artist {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.88em;
        color: {colors.get('FORTE', '#8c3b3b')};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.35), 0 1px 1px rgba({staff},0.4), 1px 2px 0 {outline};
    }}
```

- [ ] **Step 2: Step down `.thread-label`**

Replace:

```python
    .thread-label {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.85em;
        font-style: italic;
        color: rgba({score_rgb}, 0.28);
        text-shadow: 0 1px 0 {lite_c};
    }}
```

with:

```python
    .thread-label {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.75em;
        font-style: italic;
        color: rgba({score_rgb}, 0.28);
        text-shadow: 0 1px 0 {lite_c};
    }}
```

- [ ] **Step 3: Step down `.tech-badge`/`.tag-chip` and `.small-badge`**

Replace:

```python
    .tech-badge, .tag-chip {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.8em;
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        padding: 2px 6px;
        border-radius: 6px;
        border: 1px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight_press}, {hem(2, puff=False)};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.40), 0 1px 1px rgba({staff},0.4);
    }}
```

with:

```python
    .tech-badge, .tag-chip {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.72em;
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        padding: 2px 6px;
        border-radius: 6px;
        border: 1px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight_press}, {hem(2, puff=False)};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.40), 0 1px 1px rgba({staff},0.4);
    }}
```

Then replace:

```python
    .small-badge {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.7em;
        background-color: {colors.get('MUTE', '#e5dcce')};
        color: {colors.get('BAR', '#6b6b70')};
        padding: 2px 6px;
        border-radius: 5px;
    }}
```

with:

```python
    .small-badge {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.65em;
        background-color: {colors.get('MUTE', '#e5dcce')};
        color: {colors.get('BAR', '#6b6b70')};
        padding: 2px 6px;
        border-radius: 5px;
    }}
```

- [ ] **Step 4: Step down `.ribbon-label` and `.pennant-label`**

Replace:

```python
    .ribbon-label {{
        font-weight: 900;
        font-size: 0.78em;
        letter-spacing: 0.08em;
        color: {outline};
        text-shadow: 0 1px 0 rgba(255,255,255,0.25);
    }}

    .pennant-label {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.75em;
        color: {outline};
        text-shadow: 0 1px 0 rgba(255,255,255,0.25);
    }}
```

with:

```python
    .ribbon-label {{
        font-weight: 900;
        font-size: 0.7em;
        letter-spacing: 0.08em;
        color: {outline};
        text-shadow: 0 1px 0 rgba(255,255,255,0.25);
    }}

    .pennant-label {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.7em;
        color: {outline};
        text-shadow: 0 1px 0 rgba(255,255,255,0.25);
    }}
```

- [ ] **Step 5: Step down `.knob-tag` and `.brand-tag`**

Replace:

```python
    .knob-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.62em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.05em;
        text-shadow: 0 1px 0 {lite_c};
    }}
```

with:

```python
    .knob-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.58em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.05em;
        text-shadow: 0 1px 0 {lite_c};
    }}
```

Then replace:

```python
    .brand-tag {{
        font-family: "Courier New", monospace;
        font-size: 0.6em;
        letter-spacing: 0.08em;
        color: rgba({score_rgb}, 0.45);
        background-color: {colors.get('HALL', '#2c2c30')};
        border: 1px dashed {thread};
        border-radius: 4px;
        padding: 2px 6px;
        margin: 6px;
    }}
```

with:

```python
    .brand-tag {{
        font-family: "Courier New", monospace;
        font-size: 0.56em;
        letter-spacing: 0.08em;
        color: rgba({score_rgb}, 0.45);
        background-color: {colors.get('HALL', '#2c2c30')};
        border: 1px dashed {thread};
        border-radius: 4px;
        padding: 2px 6px;
        margin: 6px;
    }}
```

- [ ] **Step 6: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 7: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "feat(sqlch-gui): step down text sizes across badges/labels"
```

---

## Task 6: New `.field-entry` CSS + apply to unstyled entries

**Files:**
- Modify: `sqlch_gui/ui/common.py` (new `.field-entry` class)
- Modify: `sqlch_gui/ui/station_list.py:31-46` (`filter_entry`, `ent_name`, `ent_url`)
- Modify: `sqlch_gui/ui/discover.py:22-24` (`ent_query`)

`filter_entry`, `ent_name`, `ent_url`, and `ent_query` are plain `Gtk.Entry` widgets today with no custom CSS class, so they render as default GTK entries that clash with the dashed-fabric look everywhere else. This adds a shared class matching the existing `.context-menu entry` treatment and applies it to all four.

- [ ] **Step 1: Add the `.field-entry` CSS class**

In `sqlch_gui/ui/common.py`, replace:

```python
    .menu-btn.destructive-action:hover {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        border-color: transparent;
    }}

    /* Album Deck Outer Container - baseline rotation state */
```

with:

```python
    .menu-btn.destructive-action:hover {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        border-color: transparent;
    }}

    .field-entry {{
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        border-radius: 8px;
        padding: 4px 8px;
        border: 2px dashed {thread};
        box-shadow: 0 0 0 1px transparent, {slight_press}, {hem(2, puff=False)};
    }}
    .field-entry:focus-within {{
        border: 2px dashed {colors.get('ROOT', '#f4b84b')};
        box-shadow: 0 0 0 2px {colors.get('ROOT', '#f4b84b')};
    }}

    /* Album Deck Outer Container - baseline rotation state */
```

- [ ] **Step 2: Verify `common.py` syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 3: Apply `.field-entry` to Library's filter/add-station entries**

In `sqlch_gui/ui/station_list.py`, replace:

```python
        # Inline catalog text filtering bar
        self.filter_entry = Gtk.Entry(placeholder_text="Filter local library...")
        self.filter_entry.connect("changed", self.on_filter_changed)
        self.append(self.filter_entry)

        # Add manual configuration trigger bar
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.add_css_class("list-header")
        self.ent_name = Gtk.Entry(placeholder_text="Station Name")
        self.ent_name.set_hexpand(True)
        self.ent_url = Gtk.Entry(placeholder_text="Stream URL")
        self.ent_url.set_hexpand(True)
```

with:

```python
        # Inline catalog text filtering bar
        self.filter_entry = Gtk.Entry(placeholder_text="Filter local library...")
        self.filter_entry.add_css_class("field-entry")
        self.filter_entry.connect("changed", self.on_filter_changed)
        self.append(self.filter_entry)

        # Add manual configuration trigger bar
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.add_css_class("list-header")
        self.ent_name = Gtk.Entry(placeholder_text="Station Name")
        self.ent_name.set_hexpand(True)
        self.ent_name.add_css_class("field-entry")
        self.ent_url = Gtk.Entry(placeholder_text="Stream URL")
        self.ent_url.set_hexpand(True)
        self.ent_url.add_css_class("field-entry")
```

- [ ] **Step 4: Verify `station_list.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/station_list.py').read())"
```

Expected: no output

- [ ] **Step 5: Apply `.field-entry` to Discover's search entry**

In `sqlch_gui/ui/discover.py`, replace:

```python
        self.ent_query = Gtk.Entry(placeholder_text="Search worldwide directory...")
        self.ent_query.set_hexpand(True)
        self.ent_query.connect("activate", self.on_search)
```

with:

```python
        self.ent_query = Gtk.Entry(placeholder_text="Search worldwide directory...")
        self.ent_query.set_hexpand(True)
        self.ent_query.add_css_class("field-entry")
        self.ent_query.connect("activate", self.on_search)
```

- [ ] **Step 6: Verify `discover.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/discover.py').read())"
```

Expected: no output

- [ ] **Step 7: Manually verify in the running app**

Launch the dev build (see the Dev Launch note above). Open Library — the filter entry and the add-station Name/URL fields now show a dashed border and tight padding matching the surrounding card, instead of a plain white GTK entry. Open Discover — the search entry has the same look. Typing in each still works (filtering, add-station, and search all still function).

- [ ] **Step 8: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py sqlch_gui/ui/station_list.py sqlch_gui/ui/discover.py
git commit -m "feat(sqlch-gui): dashed-fabric styling for filter/search/add-station entries"
```

---

## Task 7: ThreadSlider (volume) resize

**Files:**
- Modify: `sqlch_gui/ui/controls.py:55-67` (constants, `set_size_request`)
- Modify: `sqlch_gui/ui/controls.py:~166-201` (button/dimple/ghost-marker draw sizes)

- [ ] **Step 1: Scale the geometry constants**

In `sqlch_gui/ui/controls.py`, replace:

```python
    # Single source of truth for the button's edge margin and the nub's
    # geometry, so drawing and hit-testing can never drift apart.
    _MARGIN = 10.0
    _NUB_GAP = 10.0
    _NUB_ZONE = 34.0
    _NUB_RADIUS_X = 9.0
    _NUB_RADIUS_Y = 13.0
```

with:

```python
    # Single source of truth for the button's edge margin and the nub's
    # geometry, so drawing and hit-testing can never drift apart.
    _MARGIN = 8.0
    _NUB_GAP = 7.0
    _NUB_ZONE = 26.0
    _NUB_RADIUS_X = 7.0
    _NUB_RADIUS_Y = 10.0
```

- [ ] **Step 2: Shrink the widget's height**

Replace:

```python
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 34)
```

with:

```python
        self.set_focusable(True)
        self.set_hexpand(True)
        self.set_size_request(-1, 26)
```

- [ ] **Step 3: Shrink the tufted button and its ghost marker**

Replace:

```python
        if self.boosted:
            # Ghost marker: a faint ring at the resting spot the button
            # will return to once un-boosted.
            cr.save()
            cr.set_dash([1.5, 1.5])
            cr.set_line_width(1.2)
            cr.set_source_rgba(*thread_rgb, 0.5)
            cr.arc(thread_x, cy, 3.0, 0, 2 * math.pi)
            cr.stroke()
            cr.restore()
```

with:

```python
        if self.boosted:
            # Ghost marker: a faint ring at the resting spot the button
            # will return to once un-boosted.
            cr.save()
            cr.set_dash([1.5, 1.5])
            cr.set_line_width(1.2)
            cr.set_source_rgba(*thread_rgb, 0.5)
            cr.arc(thread_x, cy, 2.2, 0, 2 * math.pi)
            cr.stroke()
            cr.restore()
```

Then replace:

```python
        # Tufted button: domed radial gradient, single center dimple,
        # four pull-lines radiating out to the puckered fabric edge --
        # the chesterfield-upholstery look, not a sew-through button.
        radius = 15.0
```

with:

```python
        # Tufted button: domed radial gradient, single center dimple,
        # four pull-lines radiating out to the puckered fabric edge --
        # the chesterfield-upholstery look, not a sew-through button.
        radius = 11.0
```

Then replace:

```python
        cr.set_source_rgba(*dimple_rgb, 1.0)
        cr.arc(button_x, cy, 2.6, 0, 2 * math.pi)
        cr.fill()
```

with:

```python
        cr.set_source_rgba(*dimple_rgb, 1.0)
        cr.arc(button_x, cy, 2.0, 0, 2 * math.pi)
        cr.fill()
```

- [ ] **Step 4: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output

- [ ] **Step 5: Manually verify in the running app**

Launch the dev build. The volume slider is visibly shorter (~26px vs ~34px), the tufted button and empty nub loop are proportionally smaller but the same shape. Click-to-jump, drag, scroll-to-nudge, and drag-onto-nub boost still all work.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py
git commit -m "feat(sqlch-gui): shrink ThreadSlider volume control"
```

---

## Task 8: RecordBubble + NavColumn resize

**Files:**
- Modify: `sqlch_gui/ui/controls.py:320-326` (`RecordBubble.__init__`)
- Modify: `sqlch_gui/ui/controls.py:368-371` (`RecordBubble._on_draw`)
- Modify: `sqlch_gui/ui/controls.py:448-451` (`NavColumn._spool`)

- [ ] **Step 1: Shrink `RecordBubble`'s size**

In `sqlch_gui/ui/controls.py`, replace:

```python
    def __init__(self):
        super().__init__()
        self.mode = "full"
        self.recording = False
        self.set_size_request(46, 46)
        self.set_focusable(True)
```

with:

```python
    def __init__(self):
        super().__init__()
        self.mode = "full"
        self.recording = False
        self.set_size_request(34, 34)
        self.set_focusable(True)
```

- [ ] **Step 2: Adjust the bubble's radius inset to match**

Replace:

```python
    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 5.0
```

with:

```python
    def _on_draw(self, area, cr, width, height, user_data=None):
        cx = width / 2.0
        cy = height / 2.0
        radius = min(width, height) / 2.0 - 4.0
```

- [ ] **Step 3: Shrink `NavColumn`'s spool glyph**

Replace:

```python
        self._spool = Gtk.DrawingArea()
        self._spool.set_content_width(18)
        self._spool.set_content_height(18)
        self._spool.set_draw_func(self._draw_spool)
```

with:

```python
        self._spool = Gtk.DrawingArea()
        self._spool.set_content_width(14)
        self._spool.set_content_height(14)
        self._spool.set_draw_func(self._draw_spool)
```

- [ ] **Step 4: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/controls.py').read())"
```

Expected: no output

- [ ] **Step 5: Manually verify in the running app**

Launch the dev build. The REC bubble is visibly smaller (~34px) but keeps its convex/pressed-dimple look in both states; left-click still toggles recording, right-click still cycles FULL/TRACK. The Mini nav button's spool glyph is smaller but still reads as two dashed rims + spindle.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/controls.py
git commit -m "feat(sqlch-gui): shrink RecordBubble and NavColumn spool glyph"
```

---

## Task 9: EqStrip default size + mini-row call site

**Files:**
- Modify: `sqlch_gui/ui/eq_strip.py:30` (`EqStrip.__init__` defaults)
- Modify: `sqlch_gui/ui/station_list.py:150` (mini `EqStrip` call site)

- [ ] **Step 1: Shrink the default strip size**

In `sqlch_gui/ui/eq_strip.py`, replace:

```python
    def __init__(self, n_beads: int = 7, width: int = 90, height: int = 24):
```

with:

```python
    def __init__(self, n_beads: int = 7, width: int = 68, height: int = 18):
```

(`now_playing.py` constructs this with `EqStrip()` and no args, so the big strip on the Now Playing card picks up the new default automatically.)

- [ ] **Step 2: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/eq_strip.py').read())"
```

Expected: no output

- [ ] **Step 3: Shrink the per-row mini strip in the Library list**

In `sqlch_gui/ui/station_list.py`, replace:

```python
                mini_eq = EqStrip(n_beads=3, width=22, height=14)
                mini_eq.set_valign(Gtk.Align.CENTER)
```

with:

```python
                mini_eq = EqStrip(n_beads=3, width=18, height=11)
                mini_eq.set_valign(Gtk.Align.CENTER)
```

- [ ] **Step 4: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/station_list.py').read())"
```

Expected: no output

- [ ] **Step 5: Manually verify in the running app**

Launch the dev build. Play a station — the big EQ bead strip below the cover art is visibly smaller but still bobs while playing and settles flat when paused/stopped. In the Library list, a currently-playing row's mini EQ strip is smaller too.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/eq_strip.py sqlch_gui/ui/station_list.py
git commit -m "feat(sqlch-gui): shrink EqStrip default and per-row mini size"
```

---

## Task 10: Now Playing card sizing + spacing

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py` (cover art pixel sizes, box spacing)

- [ ] **Step 1: Shrink cover art pixel size and the tracklist back-plate**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        # Hero cover art elements (Front side)
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(130)
```

with:

```python
        # Hero cover art elements (Front side)
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(98)
```

Then replace:

```python
        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(130, 130)
        track_scroll.add_css_class("art-card-back")
```

with:

```python
        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(98, 98)
        track_scroll.add_css_class("art-card-back")
```

Then replace:

```python
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 130, 130, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
```

with:

```python
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 98, 98, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
```

- [ ] **Step 2: Tighten the panel's outer box and card spacing**

Replace:

```python
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("card")

        # --- Flanked album deck: nav column / art / transport column ---
        deck_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        deck_box.set_halign(Gtk.Align.CENTER)
```

with:

```python
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.set_margin_start(3)
        self.set_margin_end(3)
        self.set_margin_top(3)
        self.set_margin_bottom(3)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")

        # --- Flanked album deck: nav column / art / transport column ---
        deck_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        deck_box.set_halign(Gtk.Align.CENTER)
```

- [ ] **Step 3: Tighten the text block, transport column, readout, and volume row spacing**

Replace:

```python
        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        text_box.set_halign(Gtk.Align.CENTER)
```

with:

```python
        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_halign(Gtk.Align.CENTER)
```

Then replace:

```python
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_col.set_valign(Gtk.Align.CENTER)
        right_col.append(rec_wrap)
```

with:

```python
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_col.set_valign(Gtk.Align.CENTER)
        right_col.append(rec_wrap)
```

Then replace:

```python
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_row.append(self.vol_slider)
        card.append(vol_row)
```

with:

```python
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vol_row.append(self.vol_slider)
        card.append(vol_row)
```

Then replace:

```python
        # Readout strip
        self.tech_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.tech_box.set_halign(Gtk.Align.CENTER)
```

with:

```python
        # Readout strip
        self.tech_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.tech_box.set_halign(Gtk.Align.CENTER)
```

- [ ] **Step 4: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 5: Manually verify in the running app**

Launch the dev build and play a station with cover art (or check the placeholder). The art is visibly smaller (~98px) and everything below it (text, volume, readout) sits tighter together, but all rows are still readable and nothing overlaps or clips. Flip to the tracklist back-plate — it's the same 98px square as the front.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): shrink cover art and tighten Now Playing card spacing"
```

---

## Task 11: Library + Discover margins/spacing

**Files:**
- Modify: `sqlch_gui/ui/station_list.py` (outer margins, box spacing)
- Modify: `sqlch_gui/ui/discover.py` (outer margins, box spacing)

- [ ] **Step 1: Tighten `StationListPanel`'s outer margins and spacing**

In `sqlch_gui/ui/station_list.py`, replace:

```python
class StationListPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.win = parent_window
```

with:

```python
class StationListPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.win = parent_window
```

Then replace:

```python
        # Add manual configuration trigger bar
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.add_css_class("list-header")
```

with:

```python
        # Add manual configuration trigger bar
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        add_box.add_css_class("list-header")
```

Then replace:

```python
            for s in sorted(groups[g_name], key=lambda x: _freq(x.get("frequency"))):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.add_css_class("station-row")
```

with:

```python
            for s in sorted(groups[g_name], key=lambda x: _freq(x.get("frequency"))):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                row.add_css_class("station-row")
```

- [ ] **Step 2: Verify `station_list.py` syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/station_list.py').read())"
```

Expected: no output

- [ ] **Step 3: Tighten `DiscoverPanel`'s outer margins and spacing**

In `sqlch_gui/ui/discover.py`, replace:

```python
class DiscoverPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.win = parent_window

        # Execution query controls
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
```

with:

```python
class DiscoverPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.win = parent_window

        # Execution query controls
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
```

Then replace:

```python
        # Scoped Container for Category Discovery
        self.discovery_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
```

with:

```python
        # Scoped Container for Category Discovery
        self.discovery_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
```

Then replace:

```python
        self.tag_grid.set_row_spacing(6)
        self.tag_grid.set_column_spacing(6)
```

with:

```python
        self.tag_grid.set_row_spacing(4)
        self.tag_grid.set_column_spacing(4)
```

Then replace:

```python
        # Reset active selection banner
        self.reset_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
```

with:

```python
        # Reset active selection banner
        self.reset_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
```

Then replace:

```python
        for r in results:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.set_margin_top(4)
            row.set_margin_bottom(4)
```

with:

```python
        for r in results:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            row.set_margin_top(3)
            row.set_margin_bottom(3)
```

- [ ] **Step 4: Verify `discover.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/discover.py').read())"
```

Expected: no output

- [ ] **Step 5: Manually verify in the running app**

Launch the dev build. Open Library — rows, the add-station bar, and the outer padding around the whole panel are visibly tighter than before, filtering and add/edit/delete still work. Open Discover — the genre-tag grid is tighter (smaller gaps between pennants), search results list is tighter, search/import still work.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/station_list.py sqlch_gui/ui/discover.py
git commit -m "feat(sqlch-gui): tighten Library and Discover panel margins/spacing"
```

---

## Task 12: Full-pass manual QA

**Files:** none (verification only, no code changes)

This task exercises the spec's full Testing checklist end to end, now that every prior task's changes are combined. No commit at the end — if something needs a follow-up tweak, note it and address it as a small fixup on top of the relevant task's commit rather than reopening this task.

- [ ] **Step 1: First-launch size check**

Kill any running dev instance (`pkill -f "python3 -m sqlch_gui"` in its own command), then launch the dev build per the Dev Launch note. Confirm the window opens noticeably smaller (~290px wide vs. the old ~380px) and every element in the Now Playing card (art, buttons, text, volume, readout) is visibly smaller but still legible.

- [ ] **Step 2: Clickability check**

With the window open, click the nav rail buttons (Mini/Library/Discover), the play/pause button, Stop, Mute, and the REC bubble. Drag the volume slider's button along the thread and onto the boost nub. Confirm every one of these is still comfortably clickable/draggable at the smaller size — none should feel fiddly or require pixel-precise aim.

- [ ] **Step 3: Library drawer check**

Click Library. Confirm the drawer opens and caps at the new smaller max-height (~320px ceiling, further capped to fit the monitor as before), rows are visibly tighter than before, the filter entry has the new dashed-fabric look, and typing into it still filters the list live.

- [ ] **Step 4: Discover panel check**

Click Discover. Confirm the genre-tag grid and search results are equally tighter, the search entry has the new `.field-entry` look, searching by text and importing a result both still work.

- [ ] **Step 5: Cross-theme check**

Switch the active palette (swap `~/.config/waybar/palette.sh` to a different generated theme, or set `SQLCH_GUI_PALETTE` to point at one), and confirm the app re-skins live (per the existing file-watch behavior) with the new `.field-entry` styling reading correctly in both a light-leaning and a dark-leaning palette — it should use `SCORE`/`STAGE`/`WING`/thread colors, never a hardcoded hex.

- [ ] **Step 6: Drawer motion check**

Drag the torn-seam handle open and closed a few times. Confirm the spring-snap animation and drag-to-open/fling behavior feel unchanged from before this change (only the drawer's max-height ceiling changed, not its physics constants).

- [ ] **Step 7: Kill the dev instance**

Find and kill the dev instance's PID once all checks pass, so it isn't left running in the background.
