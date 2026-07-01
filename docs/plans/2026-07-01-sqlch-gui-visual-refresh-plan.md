# sqlch-gui Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the dead space in sqlch-gui's three panels (hero cover art on Now Playing, tag chip + live track on Station List, genre grid on Discover) and rebalance the neubrutalist shadow/border weight so it reads as bold rather than balloony.

**Architecture:** Task 1 adds new palette default keys the CSS will reference. Task 2 does the full CSS pass in `common.py` (background gradients, tightened inner shadows, bumped nav-btn shadows, two new shared classes). Tasks 3–7 apply per-panel changes, ordered so each new method/signature exists before the task that calls it (`now_playing.get_current_track()` in Task 3 before `window.py` uses it in Task 6; `station_list.set_active()`'s new signature in Task 5 before Task 6).

**Tech Stack:** Python 3.12, GTK4 + Gtk4LayerShell (PyGObject), no existing test framework in this repo — pure-logic changes are verified with inline `python3 -c` assertions (matching this repo's existing plan conventions, see `docs/plans/2026-04-01-code-review-fixes.md`); GTK widget/CSS changes are verified by running the app.

**Spec:** `docs/plans/2026-07-01-sqlch-gui-visual-refresh-design.md`

---

## Task 1: Add gradient palette defaults

**Files:**
- Modify: `sqlch_gui/palette.py:7-23` (`_DEFAULTS` dict)

The active `raven` theme's `palette.sh` already defines `GRAD_HALL_HI`, `GRAD_HALL_LO`, `GRAD_STAGE_HI`, `GRAD_STAGE_LO`, but `_DEFAULTS` (the Rosé Pine Moon fallback used when no `palette.sh` is found, or when a theme's file is missing a key) does not. Task 2's CSS will read these four keys unconditionally, so any theme missing them would hit a `KeyError`. Add fallback values derived the same way the existing raven values were (a lighter and darker step off the base `HALL`/`STAGE` colors).

- [ ] **Step 1: Write the failing check**

```bash
python3 -c "
from sqlch_gui import palette
d = palette._DEFAULTS
for k in ('GRAD_HALL_HI', 'GRAD_HALL_LO', 'GRAD_STAGE_HI', 'GRAD_STAGE_LO'):
    assert k in d, f'{k} missing from _DEFAULTS'
print('OK')
"
```

- [ ] **Step 2: Run it to verify it fails**

Run the command from Step 1.
Expected: `AssertionError: GRAD_HALL_HI missing from _DEFAULTS`

- [ ] **Step 3: Add the defaults**

In `sqlch_gui/palette.py`, add four keys to `_DEFAULTS` right after `"SHADOW": "#0f0e17",`:

```python
    "SHADOW": "#0f0e17",
    "GRAD_HALL_HI": "#282544",
    "GRAD_HALL_LO": "#1a1828",
    "GRAD_STAGE_HI": "#302c4d",
    "GRAD_STAGE_LO": "#211f36",
    "STAFF": "15,14,23",
```

- [ ] **Step 4: Run the check again to verify it passes**

Run the command from Step 1.
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/palette.py
git commit -m "feat(sqlch-gui): add gradient fallback defaults to palette"
```

---

## Task 2: CSS pass — background gradients, tightened shadows, new shared classes

**Files:**
- Modify: `sqlch_gui/ui/common.py:17-162` (the `css` f-string in `load_custom_css()`)

This is the full visual-style change from the spec: gradients on the two biggest flat surfaces, normalized shadow weight on inner elements, bumped weight on nav buttons, and two new classes (`.tag-chip`, `.station-live`) that Tasks 5 and 7 will use.

- [ ] **Step 1: Change `box.popup-window` and `.sidebar` to gradient backgrounds**

In `sqlch_gui/ui/common.py`, replace:

```python
    box.popup-window {{
        background-color: {colors['HALL']};
        color: {colors['SCORE']};
        border: 3px solid {outline};
        border-radius: 10px;
        box-shadow: 10px 10px 0 {shadow};
        margin: 4px 18px 18px 4px;
    }}
    .sidebar {{
        background-color: {colors['STAGE']};
        border: 3px solid {outline};
        border-radius: 10px;
        padding: 6px;
        box-shadow: 6px 6px 0 {shadow};
        margin: 10px 4px 10px 0;
    }}
```

with:

```python
    box.popup-window {{
        background-image: linear-gradient(160deg, {colors['GRAD_HALL_HI']}, {colors['GRAD_HALL_LO']});
        color: {colors['SCORE']};
        border: 3px solid {outline};
        border-radius: 10px;
        box-shadow: 10px 10px 0 {shadow};
        margin: 4px 18px 18px 4px;
    }}
    .sidebar {{
        background-image: linear-gradient(160deg, {colors['GRAD_STAGE_HI']}, {colors['GRAD_STAGE_LO']});
        border: 3px solid {outline};
        border-radius: 10px;
        padding: 6px;
        box-shadow: 6px 6px 0 {shadow};
        margin: 10px 4px 10px 0;
    }}
```

(The window/sidebar border and shadow weight are unchanged — this task only touches the outer chrome's background fill, not its border/shadow weight.)

- [ ] **Step 2: Bump nav-btn hover/active shadow weight**

Replace:

```python
    .nav-btn:hover {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 2px solid {outline};
        box-shadow: 2px 2px 0 {shadow};
    }}
    .nav-btn.active {{
        background-color: {colors['ROOT']};
        color: {colors['HALL']};
        font-weight: bold;
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 {shadow};
    }}
```

with:

```python
    .nav-btn:hover {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 2px solid {outline};
        box-shadow: 4px 4px 0 {shadow};
    }}
    .nav-btn.active {{
        background-color: {colors['ROOT']};
        color: {colors['HALL']};
        font-weight: bold;
        border: 2px solid {outline};
        box-shadow: 5px 5px 0 {shadow};
    }}
```

- [ ] **Step 3: Tighten `.card`, `.cover-art`, `.list-header` shadow weight to 4px, bump `.cover-art` size to 120px**

Replace:

```python
    .card {{
        background-color: {colors['STAGE']};
        border: 2px solid {outline};
        border-radius: 8px;
        padding: 12px;
        box-shadow: 5px 5px 0 {shadow};
    }}
    .cover-art {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        border-radius: 6px;
        min-width: 80px;
        min-height: 80px;
        box-shadow: 3px 3px 0 {shadow};
    }}
    .list-header {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        font-weight: bold;
        border: 2px solid {outline};
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 12px;
        box-shadow: 3px 3px 0 {shadow};
    }}
```

with:

```python
    .card {{
        background-color: {colors['STAGE']};
        border: 2px solid {outline};
        border-radius: 8px;
        padding: 12px;
        box-shadow: 4px 4px 0 {shadow};
    }}
    .cover-art {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        border-radius: 6px;
        min-width: 120px;
        min-height: 120px;
        box-shadow: 4px 4px 0 {shadow};
    }}
    .list-header {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        font-weight: bold;
        border: 2px solid {outline};
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 12px;
        box-shadow: 4px 4px 0 {shadow};
    }}
```

- [ ] **Step 4: Tighten `.station-row:hover` and `.station-row.active` shadow weight to 4px**

Replace:

```python
    .station-row:hover {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        box-shadow: 2px 2px 0 {shadow};
    }}
    .station-row.active {{
        background-color: {colors['SEVENTH']};
        color: {colors['HALL']};
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 {shadow};
    }}
```

with:

```python
    .station-row:hover {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        box-shadow: 4px 4px 0 {shadow};
    }}
    .station-row.active {{
        background-color: {colors['SEVENTH']};
        color: {colors['HALL']};
        border: 2px solid {outline};
        box-shadow: 4px 4px 0 {shadow};
    }}
```

- [ ] **Step 5: Tighten `.control-btn:hover` shadow weight to match the 4px base**

Replace:

```python
    .control-btn:hover {{
        background-color: {colors['MUTE']};
        box-shadow: 5px 5px 0 {shadow};
    }}
```

with:

```python
    .control-btn:hover {{
        background-color: {colors['MUTE']};
        box-shadow: 4px 4px 0 {shadow};
    }}
```

(`.control-btn`'s base state and `.control-btn:active`'s press animation are unchanged — the base was already 2px border / 4px shadow, the target weight.)

- [ ] **Step 6: Add `.tag-chip` and `.station-live` classes**

Add these two new rules at the end of the `css` f-string, right before the closing `"""` (after the existing `.tech-badge` block):

```python
    .tag-chip {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 1.5px solid {outline};
        border-radius: 12px;
        padding: 4px 10px;
        font-size: 0.75em;
        box-shadow: 2px 2px 0 {shadow};
    }}
    .tag-chip:hover {{
        background-color: {colors['MUTE']};
    }}
    .station-live {{
        font-size: 0.8em;
        font-style: italic;
        color: {colors['FIFTH']};
    }}
    .station-row.active .station-live {{
        color: {colors['HALL']};
    }}
    """
```

(Only the final `"""` line moves — everything above it in this step is new.)

- [ ] **Step 7: Manually verify the CSS loads without error**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"`
Expected: no output (syntax is valid — this catches f-string brace mistakes before running the full GTK app)

- [ ] **Step 8: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "feat(sqlch-gui): background gradients, tightened shadow weight, tag-chip/station-live classes"
```

---

## Task 3: Now Playing hero cover art

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py:19-49` (header card construction in `__init__`)
- Modify: `sqlch_gui/ui/now_playing.py` (add `get_current_track()` method)

Turn the horizontal thumbnail+text card into a vertical, centered hero layout, and expose the current artist/title so Task 6 can pass it to the station list.

- [ ] **Step 1: Restructure the header card to vertical/centered**

In `sqlch_gui/ui/now_playing.py`, replace lines 19–49:

```python
        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.add_css_class("card")
        
        # Cover Art
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(80)
        self.cover_img.add_css_class("cover-art")
        self.clear_cover()
        card.append(self.cover_img)

        # Meta details text stack
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.lbl_title = Gtk.Label(xalign=0.0)
        self.lbl_title.add_css_class("meta-title")
        self.lbl_title.set_wrap(True)
        self.lbl_title.set_max_width_chars(28)
        
        self.lbl_artist = Gtk.Label(xalign=0.0)
        self.lbl_artist.add_css_class("meta-artist")
        self.lbl_artist.set_wrap(True)
        self.lbl_artist.set_max_width_chars(28)
        
        self.lbl_genre = Gtk.Label(xalign=0.0)
        self.lbl_genre.add_css_class("meta-genre")
        
        text_box.append(self.lbl_title)
        text_box.append(self.lbl_artist)
        text_box.append(self.lbl_genre)
        card.append(text_box)
        self.append(card)
```

with:

```python
        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")

        # Hero cover art, centered
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(120)
        self.cover_img.add_css_class("cover-art")
        self.cover_img.set_halign(Gtk.Align.CENTER)
        self.clear_cover()
        card.append(self.cover_img)

        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_halign(Gtk.Align.CENTER)
        self.lbl_title = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_title.add_css_class("meta-title")
        self.lbl_title.set_wrap(True)
        self.lbl_title.set_max_width_chars(28)
        
        self.lbl_artist = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_artist.add_css_class("meta-artist")
        self.lbl_artist.set_wrap(True)
        self.lbl_artist.set_max_width_chars(28)
        
        self.lbl_genre = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_genre.add_css_class("meta-genre")
        
        text_box.append(self.lbl_title)
        text_box.append(self.lbl_artist)
        text_box.append(self.lbl_genre)
        card.append(text_box)
        self.append(card)
```

- [ ] **Step 2: Add `get_current_track()`**

In `sqlch_gui/ui/now_playing.py`, add this method right after `get_current_id()`:

```python
    def get_current_track(self) -> tuple[str | None, str | None]:
        return self._cur_artist, self._cur_title
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"`
Expected: no output

- [ ] **Step 4: Manually verify in the running app**

Run: `python -m sqlch_gui` (or the packaged `sqlch-gui` binary), play a station, switch to the Now Playing tab.
Expected: cover art is ~120px and horizontally centered at the top of the card; title/artist/genre are centered below it, matching the approved mockup at `docs/plans/2026-07-01-sqlch-gui-visual-refresh-design.md`.

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): centered hero cover art on Now Playing panel"
```

---

## Task 4: RadioBrowser tag search

**Files:**
- Modify: `sqlch_gui/radiobrowser.py`

Extract the duplicated fetch/parse logic behind `search()` into a shared helper, then add a tag-based search that Task 7's genre grid will call. `add_from_search()` and `_search_cache` are untouched — both search paths feed the same cache.

- [ ] **Step 1: Write the failing check for the cache helper**

```bash
cd /home/prepko/sqlch
python3 -c "
from sqlch_gui import radiobrowser as rb
result = rb._cache_results([{'name': 'A'}, {'name': 'B'}])
assert result[0]['index'] == 1 and result[1]['index'] == 2, result
assert rb._search_cache == result
print('OK')
"
```

- [ ] **Step 2: Run it to verify it fails**

Run the command from Step 1.
Expected: `AttributeError: module 'sqlch_gui.radiobrowser' has no attribute '_cache_results'`

- [ ] **Step 3: Extract `_fetch_stations` and `_cache_results`, add `search_by_tag`/`run_search_by_tag`**

Replace the whole `search`/`run_search` block (lines 58–93) with:

```python
def _fetch_stations(url: str, limit: int) -> list[dict]:
    """Fetch and normalize a RadioBrowser station listing from a full query URL."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sqlch-gui/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
            return [
                {
                    "name": item.get("name", "Unknown").strip(),
                    "url": item.get("url_resolved", item.get("url", "")),
                    "favicon": item.get("favicon", ""),
                    "tags": item.get("tags", ""),
                    "country": item.get("countrycode", ""),
                }
                for item in raw[:limit]
            ]
    except Exception:
        return []


def search(query: str, limit: int = 20) -> list[dict]:
    """Execute generic title metadata directory lookup inside open streaming databases."""
    if not query.strip():
        return []
    url = f"https://{_RB_API}/json/stations/byname/{urllib.parse.quote(query)}"
    return _fetch_stations(url, limit)


def search_by_tag(tag: str, limit: int = 20) -> list[dict]:
    """Execute genre/tag directory lookup, sorted by station popularity."""
    if not tag.strip():
        return []
    url = f"https://{_RB_API}/json/stations/bytag/{urllib.parse.quote(tag)}?order=votes&reverse=true"
    return _fetch_stations(url, limit)


def _cache_results(items: list[dict]) -> list[dict]:
    """Index-map a result list into the module-level search cache used by add_from_search()."""
    global _search_cache
    _search_cache.clear()
    for i, item in enumerate(items, start=1):
        item["index"] = i
        _search_cache.append(item)
    return _search_cache


def run_search(query: str) -> list[dict]:
    """Execute structure scans across the tracking registry array and load them index-mapped."""
    return _cache_results(search(query, limit=25))


def run_search_by_tag(tag: str) -> list[dict]:
    """Execute a tag-based structure scan and load it index-mapped."""
    return _cache_results(search_by_tag(tag, limit=25))
```

- [ ] **Step 4: Run the check again to verify it passes**

Run the command from Step 1.
Expected: `OK`

- [ ] **Step 5: Verify `add_from_search` still works against the shared cache**

```bash
python3 -c "
from unittest.mock import patch
from sqlch_gui import radiobrowser as rb
with patch.object(rb, '_fetch_stations', return_value=[{'name': 'Jazz FM', 'url': 'http://x'}]):
    rb.run_search_by_tag('jazz')
assert rb._search_cache[0]['name'] == 'Jazz FM'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/radiobrowser.py
git commit -m "feat(sqlch-gui): add RadioBrowser tag search, dedupe fetch/cache logic"
```

---

## Task 5: Station List tag chip + live track preview

**Files:**
- Modify: `sqlch_gui/ui/station_list.py`

Each row gains a group tag chip and, for the active row, a live-track line. Also fixes the hardcoded group-header hex color to pull from the palette.

- [ ] **Step 1: Write the failing check for the live-text formatter**

```bash
cd /home/prepko/sqlch
python3 -c "
from sqlch_gui.ui.station_list import format_live_text
assert format_live_text('Emancipator', 'Nightswim') == '♫ Emancipator — Nightswim'
assert format_live_text(None, 'Nightswim') == '♫ Nightswim'
assert format_live_text(None, None) == ''
print('OK')
"
```

- [ ] **Step 2: Run it to verify it fails**

Run the command from Step 1.
Expected: `ImportError: cannot import name 'format_live_text'`

- [ ] **Step 3: Add `format_live_text` and the `palette` import**

In `sqlch_gui/ui/station_list.py`, change the imports at the top from:

```python
from gi.repository import Gtk, Gdk
from .. import library, daemon
```

to:

```python
from gi.repository import Gtk, Gdk
from .. import library, daemon, palette
```

Then add this module-level function right after the imports (before `class StationListPanel`):

```python
def format_live_text(artist: str | None, title: str | None) -> str:
    parts = [p for p in (artist, title) if p]
    if not parts:
        return ""
    return "♫ " + " — ".join(parts)
```

- [ ] **Step 4: Run the check again to verify it passes**

Run the command from Step 1.
Expected: `OK`

- [ ] **Step 5: Fix the hardcoded group-header color**

Replace:

```python
        for g_name in sorted(groups.keys()):
            # Inject structural separator heading label
            lbl = Gtk.Label(xalign=0.0)
            lbl.set_markup(f"<span foreground='#6e6a86' weight='bold'>{g_name}</span>")
```

with:

```python
        colors = palette.load()
        for g_name in sorted(groups.keys()):
            # Inject structural separator heading label
            lbl = Gtk.Label(xalign=0.0)
            lbl.set_markup(f"<span foreground='{colors['BAR']}' weight='bold'>{g_name}</span>")
```

- [ ] **Step 6: Add the tag chip and live-track label to each row**

Replace:

```python
            for s in sorted(groups[g_name], key=lambda x: _freq(x.get("frequency"))):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.add_css_class("station-row")

                freq_lbl = Gtk.Label()
                freq_lbl.add_css_class("station-freq")
                freq_lbl.set_text(f"{_freq(s.get('frequency')):.1f}")
                
                name_lbl = Gtk.Label(label=s.get("name"), xalign=0.0)
                name_lbl.set_hexpand(True)
                name_lbl.set_ellipsize(3) # Pango.EllipsizeMode.END
                
                row.append(freq_lbl)
                row.append(name_lbl)

                # Secondary click binding context setup
                click_gesture = Gtk.GestureClick()
                click_gesture.set_button(0)
                click_gesture.connect("released", lambda g, n, x, y, st=s: self.on_row_clicked(g, n, x, y, st))
                row.add_controller(click_gesture)

                self.list_box.append(row)
                self._rows_map[s["id"]] = row
```

with:

```python
            for s in sorted(groups[g_name], key=lambda x: _freq(x.get("frequency"))):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.add_css_class("station-row")

                freq_lbl = Gtk.Label()
                freq_lbl.add_css_class("station-freq")
                freq_lbl.set_text(f"{_freq(s.get('frequency')):.1f}")

                body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                body.set_hexpand(True)
                name_lbl = Gtk.Label(label=s.get("name"), xalign=0.0)
                name_lbl.set_ellipsize(3) # Pango.EllipsizeMode.END
                live_lbl = Gtk.Label(xalign=0.0)
                live_lbl.add_css_class("station-live")
                live_lbl.set_ellipsize(3)
                live_lbl.set_visible(False)
                body.append(name_lbl)
                body.append(live_lbl)

                tag_lbl = Gtk.Label(label=s.get("group", "Unsorted"))
                tag_lbl.add_css_class("tag-chip")

                row.append(freq_lbl)
                row.append(body)
                row.append(tag_lbl)

                # Secondary click binding context setup
                click_gesture = Gtk.GestureClick()
                click_gesture.set_button(0)
                click_gesture.connect("released", lambda g, n, x, y, st=s: self.on_row_clicked(g, n, x, y, st))
                row.add_controller(click_gesture)

                self.list_box.append(row)
                self._rows_map[s["id"]] = (row, live_lbl)
```

- [ ] **Step 7: Update `set_active` to accept and render the live track**

Replace:

```python
    def set_active(self, active_id: str | None):
        for s_id, row in self._rows_map.items():
            if s_id == active_id:
                row.add_css_class("active")
            else:
                row.remove_css_class("active")
```

with:

```python
    def set_active(self, active_id: str | None, icy_artist: str | None = None, icy_title: str | None = None):
        for s_id, (row, live_lbl) in self._rows_map.items():
            if s_id == active_id:
                row.add_css_class("active")
                text = format_live_text(icy_artist, icy_title)
                live_lbl.set_text(text)
                live_lbl.set_visible(bool(text))
            else:
                row.remove_css_class("active")
                live_lbl.set_visible(False)
```

- [ ] **Step 8: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/station_list.py').read())"`
Expected: no output

- [ ] **Step 9: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/station_list.py
git commit -m "feat(sqlch-gui): tag chip + live track preview on station rows, palette-based group header"
```

---

## Task 6: Wire current track into the station list

**Files:**
- Modify: `sqlch_gui/ui/window.py:115-122` (`_apply_daemon_state`)

`StationListPanel.set_active()` now accepts artist/title (Task 5); `NowPlayingPanel.get_current_track()` now exists (Task 3). Connect them.

- [ ] **Step 1: Pass the current track through**

In `sqlch_gui/ui/window.py`, replace:

```python
    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        self.now_playing.update_indicators(bitrate, vol, muted, self._bt_active, playing, channels)
        self.station_list.set_active(self.now_playing.get_current_id())
        return False
```

with:

```python
    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        self.now_playing.update_indicators(bitrate, vol, muted, self._bt_active, playing, channels)
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/window.py').read())"`
Expected: no output

- [ ] **Step 3: Manually verify in the running app**

Run: `python -m sqlch_gui` (or the packaged `sqlch-gui` binary), play a station with ICY metadata, switch to Station Library.
Expected: the active row shows a small italic "♫ Artist — Title" line under the station name, matching the approved mockup.

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/window.py
git commit -m "feat(sqlch-gui): thread current ICY track into station list active row"
```

---

## Task 7: Discover genre/tag browse grid

**Files:**
- Modify: `sqlch_gui/ui/discover.py`

Replace the blank pre-search empty state with a grid of genre chips that trigger `radiobrowser.run_search_by_tag()` (Task 4) through the existing async search/results pipeline.

- [ ] **Step 1: Add the tag grid, wire it to the existing search pipeline**

Replace the whole file with:

```python
"""Network Radio-Browser directory scanning interface."""

import threading
from gi.repository import Gtk, GLib
from .. import radiobrowser

GENRE_TAGS = ["Jazz", "News", "Rock", "Electronic", "Classical", "Talk", "Ambient", "Sports", "80s"]


class DiscoverPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.win = parent_window

        # Execution query controls
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.ent_query = Gtk.Entry(placeholder_text="Search worldwide directory...")
        self.ent_query.set_hexpand(True)
        self.ent_query.connect("activate", self.on_search)
        
        btn_go = Gtk.Button(icon_name="edit-find-symbolic")
        btn_go.connect("clicked", self.on_search)
        
        search_box.append(self.ent_query)
        search_box.append(btn_go)
        self.append(search_box)

        # Genre browse grid, shown until the first search of any kind
        self.tag_grid = Gtk.FlowBox()
        self.tag_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.tag_grid.set_max_children_per_line(4)
        self.tag_grid.set_row_spacing(6)
        self.tag_grid.set_column_spacing(6)
        for tag in GENRE_TAGS:
            btn = Gtk.Button(label=tag)
            btn.add_css_class("tag-chip")
            btn.connect("clicked", lambda b, t=tag: self.on_tag_clicked(t))
            self.tag_grid.append(btn)
        self.append(self.tag_grid)

        # Output catalog matrix viewport
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.results_box = Gtk.ListBox()
        self.results_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.results_box)
        self.append(scroll)
        
        self.spinner = Gtk.Spinner()
        self.append(self.spinner)

    def on_tag_clicked(self, tag: str):
        self.tag_grid.set_visible(False)
        self.spinner.start()
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        threading.Thread(target=self._async_search_by_tag, args=(tag,), daemon=True).start()

    def _async_search_by_tag(self, tag: str):
        results = radiobrowser.run_search_by_tag(tag)
        GLib.idle_add(self._apply_results, results)

    def on_search(self, widget):
        q = self.ent_query.get_text().strip()
        if not q:
            return
        self.tag_grid.set_visible(False)
        self.spinner.start()
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        threading.Thread(target=self._async_search, args=(q,), daemon=True).start()

    def _async_search(self, query: str):
        results = radiobrowser.run_search(query)
        GLib.idle_add(self._apply_results, results)

    def _apply_results(self, results: list[dict]) -> bool:
        self.spinner.stop()
        if not results:
            lbl = Gtk.Label(label="No stations matched query parameters.")
            lbl.set_margin_top(12)
            self.results_box.append(lbl)
            return False

        for r in results:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.set_margin_top(4)
            row.set_margin_bottom(4)
            
            meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            meta.set_hexpand(True)
            
            title = Gtk.Label(label=r["name"], xalign=0.0)
            title.set_ellipsize(3)
            
            sub = Gtk.Label(xalign=0.0)
            sub.add_css_class("meta-genre")
            tag_str = r.get("tags", "")[:40]
            cc = r.get("country", "")
            sub.set_text(f"[{cc}] {tag_str}" if cc else tag_str)
            
            meta.append(title)
            meta.append(sub)
            row.append(meta)
            
            btn_import = Gtk.Button(icon_name="bookmark-new-symbolic")
            btn_import.set_tooltip_text("Import into local station library")
            btn_import.connect("clicked", lambda b, idx=r["index"]: self.on_import(idx))
            row.append(btn_import)
            
            self.results_box.append(row)
        return False

    def on_import(self, index: int):
        err = radiobrowser.add_from_search(index)
        if not err and self.win:
            self.win.trigger_library_refresh()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('sqlch_gui/ui/discover.py').read())"`
Expected: no output

- [ ] **Step 3: Manually verify in the running app**

Run: `python -m sqlch_gui` (or the packaged `sqlch-gui` binary), switch to Discover.
Expected: a 3x3 grid of genre chips (Jazz, News, Rock, Electronic, Classical, Talk, Ambient, Sports, 80s) appears where the panel used to be blank, matching the approved mockup. Clicking a chip hides the grid, shows the spinner, and populates results the same way a text search does. A subsequent text search also works normally.

- [ ] **Step 4: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/discover.py
git commit -m "feat(sqlch-gui): genre/tag browse grid on Discover empty state"
```
