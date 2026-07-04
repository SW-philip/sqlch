# sqlch-gui Now Playing LBP Fabric Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six fabric/felt-language enhancements to sqlch-gui's Now Playing panel — a lit metadata caption, a decorative EQ bead strip, sewn-on corner tags, knob tick-stitching with labels, an output-device badge, and a woven brand tag — replacing an earlier idea set pitched in a literal metal/glass hardware register.

**Architecture:** Six independent-but-sequenced tasks, one per spec item. Tasks 2, 3, and 5 each add a parameter to `NowPlayingPanel.update_indicators()` and thread a new value through `window.py`'s `_daemon_monitor_loop` / `_apply_daemon_state` — they're ordered so each task's diff reflects the prior task's accumulated changes to that method's signature and body. Tasks 4 and 6 touch disjoint code (knobs; a static label) and have no ordering dependency on the others, but are kept last since they're the lowest-risk, purely-additive changes.

**Tech Stack:** Python 3.12, GTK4 + Gtk4LayerShell (PyGObject), Cairo for custom-drawn widgets (`knob.py`, new `eq_strip.py`). No existing test framework in this repo — pure-logic changes are verified with inline `python3 -c` syntax/assertion checks (matching this repo's existing plan conventions, see `docs/plans/2026-07-01-sqlch-gui-visual-refresh-plan.md`); GTK widget/CSS changes are verified by running the app.

**Spec:** `docs/plans/2026-07-04-sqlch-gui-now-playing-lbp-design.md`

---

## Task 1: Thread-brightness metadata caption

**Files:**
- Modify: `sqlch_gui/ui/common.py` (new `_hex_to_rgb` helper, `score_rgb` var, `.thread-label` / `.thread-label.lit` CSS)
- Modify: `sqlch_gui/ui/now_playing.py` (new `_set_genre` helper, wire into `update()` and `reset_ui()`)

`lbl_genre` currently hides/shows via `set_visible()`. Change it to stay permanently present, switching between a dim "unlit" placeholder and a lit gold state — reusing the existing `metadata.get_icy_genre()` value, no new data plumbing.

- [ ] **Step 1: Add the `_hex_to_rgb` helper to `common.py`**

In `sqlch_gui/ui/common.py`, replace:

```python
_css_provider: Gtk.CssProvider | None = None

def get_adaptive_thread(bg_hex: str, score_hex: str, staff_rgb: str) -> str:
```

with:

```python
_css_provider: Gtk.CssProvider | None = None

def _hex_to_rgb(hex_val: str) -> str:
    """Convert a '#rrggbb' (or '#rgb') string into a bare 'r, g, b' triple for rgba() strings."""
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r}, {g}, {b}"

def get_adaptive_thread(bg_hex: str, score_hex: str, staff_rgb: str) -> str:
```

- [ ] **Step 2: Verify the helper**

```bash
cd /home/prepko/sqlch
python3 -c "
from sqlch_gui.ui.common import _hex_to_rgb
assert _hex_to_rgb('#e8e8e8') == '232, 232, 232', _hex_to_rgb('#e8e8e8')
assert _hex_to_rgb('#fff') == '255, 255, 255', _hex_to_rgb('#fff')
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Compute `score_rgb` in `load_custom_css()`**

In `sqlch_gui/ui/common.py`, replace:

```python
    outline = colors.get('SHADOW', '#121214')
    score = colors.get('SCORE', '#121214')
    staff = colors.get('STAFF', '20,20,24')
```

with:

```python
    outline = colors.get('SHADOW', '#121214')
    score = colors.get('SCORE', '#121214')
    score_rgb = _hex_to_rgb(score)
    staff = colors.get('STAFF', '20,20,24')
```

- [ ] **Step 4: Add `.thread-label` / `.thread-label.lit` CSS**

In `sqlch_gui/ui/common.py`, replace:

```python
    .meta-genre {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.85em;
        color: {colors.get('BAR', '#6b6b70')};
        font-style: italic;
        text-shadow: 0 1px 0 {lite_c};
    }}

    .tech-badge, .tag-chip {{
```

with:

```python
    .meta-genre {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.85em;
        color: {colors.get('BAR', '#6b6b70')};
        font-style: italic;
        text-shadow: 0 1px 0 {lite_c};
    }}

    .thread-label {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.85em;
        font-style: italic;
        color: rgba({score_rgb}, 0.28);
        text-shadow: 0 1px 0 {lite_c};
    }}
    .thread-label.lit {{
        color: {colors.get('ROOT', '#f4b84b')};
        font-weight: 700;
    }}

    .tech-badge, .tag-chip {{
```

- [ ] **Step 5: Verify `common.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 6: Swap `lbl_genre`'s CSS class**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        self.lbl_genre = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_genre.add_css_class("meta-genre")
```

with:

```python
        self.lbl_genre = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_genre.add_css_class("thread-label")
```

- [ ] **Step 7: Add the `_set_genre` helper**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
    def clear_cover(self):
        self.cover_stack.set_visible_child_name("placeholder")

    def reset_ui(self):
```

with:

```python
    def clear_cover(self):
        self.cover_stack.set_visible_child_name("placeholder")

    def _set_genre(self, genre: str | None):
        if genre:
            self.lbl_genre.set_text(genre)
            self.lbl_genre.add_css_class("lit")
        else:
            self.lbl_genre.set_text("GENRE")
            self.lbl_genre.remove_css_class("lit")

    def reset_ui(self):
```

- [ ] **Step 8: Wire `_set_genre` into `reset_ui()`**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self.lbl_genre.set_text("")
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
```

with:

```python
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self._set_genre(None)
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
```

- [ ] **Step 9: Wire `_set_genre` into `update()`**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        genre = metadata.get_icy_genre()
        self.lbl_genre.set_text(genre if genre else "")
        self.lbl_genre.set_visible(bool(genre))
```

with:

```python
        genre = metadata.get_icy_genre()
        self._set_genre(genre)
```

- [ ] **Step 10: Verify `now_playing.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 11: Manually verify in the running app**

Run `python -m sqlch_gui` (or the packaged `sqlch-gui` binary). Before playing anything, the caption below the title/artist reads a dim "GENRE" instead of being blank/absent. Play a station that sends an ICY genre — the caption lights up gold with the real genre text.

- [ ] **Step 12: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): dim-to-lit thread caption for genre metadata"
```

---

## Task 2: Decorative EQ bead strip

**Files:**
- Create: `sqlch_gui/ui/eq_strip.py`
- Modify: `sqlch_gui/ui/now_playing.py` (import, construct, append, wire into `update_indicators()` / `reset_ui()`)

A row of soft fabric "beads" that bob in a procedural (non-audio-reactive) wave while a stream plays — the decorative fallback the 2026-07-01 spec tabled as future work, drawn in the same Cairo-widget idiom as `knob.py`.

- [ ] **Step 1: Create the widget**

Create `sqlch_gui/ui/eq_strip.py`:

```python
"""Decorative EQ bead strip — a non-audio-reactive procedural animation.

Revisits the "future work" item tabled in the 2026-07-01 visual refresh
spec: a real audio-reactive meter needs an mpv audio-filter pipeline
(astats/showvolume) and was judged too risky then. This is the decorative
fallback that spec named, drawn in the same Cairo-widget idiom as the
knobs in knob.py.
"""

import math
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib


class EqStrip(Gtk.DrawingArea):
    """Row of soft fabric 'beads' that bob in a procedural wave while active."""

    N_BEADS = 7
    FRAME_MS = 80

    def __init__(self):
        super().__init__()
        self.set_size_request(90, 24)
        self._phase = 0.0
        self._running = False
        self._timer_id = None
        self.set_draw_func(self._on_draw)

    def set_active(self, active: bool):
        if active == self._running:
            return
        self._running = active
        if active and self._timer_id is None:
            self._timer_id = GLib.timeout_add(self.FRAME_MS, self._tick)
        elif not active and self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
            self._phase = 0.0
            self.queue_draw()

    def _tick(self) -> bool:
        self._phase += 0.35
        self.queue_draw()
        return self._running

    def _on_draw(self, area, cr, width, height, user_data=None):
        n = self.N_BEADS
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

            cr.set_source_rgba(0.96, 0.72, 0.24, 1.0)
            self._rounded_bar(cr, x, y, bead_w, bead_h)
            cr.fill()

    @staticmethod
    def _rounded_bar(cr, x, y, w, h):
        r = min(w / 2.0, h / 2.0, 4.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/eq_strip.py').read())"
```

Expected: no output

- [ ] **Step 3: Import `EqStrip` in `now_playing.py`**

Replace:

```python
from .. import daemon, metadata
from .knob import RotaryKnob, RecordKnob
```

with:

```python
from .. import daemon, metadata
from .knob import RotaryKnob, RecordKnob
from .eq_strip import EqStrip
```

- [ ] **Step 4: Construct and append the strip below the cover art**

Replace:

```python
        card.append(deck_box)

        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
```

with:

```python
        card.append(deck_box)

        self.eq_strip = EqStrip()
        self.eq_strip.set_halign(Gtk.Align.CENTER)
        card.append(self.eq_strip)

        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
```

- [ ] **Step 5: Stop the animation in `reset_ui()`**

Replace:

```python
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self._set_genre(None)
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.lbl_bitrate.set_visible(False)
```

with:

```python
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self._set_genre(None)
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.eq_strip.set_active(False)
        self.lbl_bitrate.set_visible(False)
```

- [ ] **Step 6: Drive the animation from `update_indicators()`**

Replace:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None):
        self._loaded = playing
        self.btn_toggle.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")

        # Block signals temporarily to prevent loopback configuration cascades
```

with:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None):
        self._loaded = playing
        self.btn_toggle.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")
        self.eq_strip.set_active(playing)

        # Block signals temporarily to prevent loopback configuration cascades
```

- [ ] **Step 7: Verify `now_playing.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 8: Manually verify in the running app**

Run the app. With nothing playing, the bead strip sits low and still. Play a station — the beads bob in a wave. Pause/stop — they settle back down.

- [ ] **Step 9: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/eq_strip.py sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): decorative EQ bead strip on Now Playing"
```

---

## Task 3: Corner tags (LIVE / format badge)

**Files:**
- Modify: `sqlch_gui/ui/common.py` (`.corner-tag`, `.corner-tag-left`, `.corner-tag-right` CSS)
- Modify: `sqlch_gui/daemon.py` (`get_stream_format()`)
- Modify: `sqlch_gui/ui/now_playing.py` (overlay + tag widgets, LIVE wiring in `update()`, format param in `update_indicators()`, hide both in `reset_ui()`)
- Modify: `sqlch_gui/ui/window.py` (thread `fmt` through the monitor loop)

Two small crooked label pills overlaid on the cover-art corners: LIVE for streams with no track metadata, and a format badge (e.g. "MP3") sourced the same way bitrate/channels already are.

- [ ] **Step 1: Add corner-tag CSS**

In `sqlch_gui/ui/common.py`, replace:

```python
    .cover-glyph {{
        font-size: 58px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}

    .list-plate {{
```

with:

```python
    .cover-glyph {{
        font-size: 58px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}

    .corner-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.65em;
        padding: 2px 7px;
        border-radius: 8px;
        box-shadow: 0 2px 0 rgba({staff}, 0.4);
        margin: 5px;
    }}
    .corner-tag-left {{
        background-color: {colors.get('ROOT', '#f4b84b')};
        color: {outline};
        transform: rotate(-4deg);
    }}
    .corner-tag-right {{
        background-color: {colors.get('BAR', '#6a6a6a')};
        color: {score};
        transform: rotate(4deg);
    }}

    .list-plate {{
```

- [ ] **Step 2: Verify `common.py` syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 3: Add `get_stream_format()` to `daemon.py`**

Replace:

```python
def get_stream_channels() -> int | None:
    """Return channel count from MPV (1 = mono, 2 = stereo), or None."""
    val = _mpv_get_property("audio-params/channel-count")
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None
```

with:

```python
def get_stream_channels() -> int | None:
    """Return channel count from MPV (1 = mono, 2 = stereo), or None."""
    val = _mpv_get_property("audio-params/channel-count")
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


def get_stream_format() -> str | None:
    """Return the short audio codec name (e.g. 'mp3', 'aac') from MPV, or None."""
    val = _mpv_get_property("audio-codec-name")
    if val:
        return str(val).upper()
    return None
```

- [ ] **Step 4: Verify `daemon.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/daemon.py').read())"
```

Expected: no output

- [ ] **Step 5: Wrap the cover art in an `Overlay` with the two tag labels**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        # Main stitched wrap framework
        self.stack_wrapper = Gtk.Box()
        self.stack_wrapper.add_css_class("album-deck-wrapper")
        self.stack_wrapper.append(self.deck_stack)
        deck_box.append(self.stack_wrapper)
```

with:

```python
        # Main stitched wrap framework
        self.stack_wrapper = Gtk.Box()
        self.stack_wrapper.add_css_class("album-deck-wrapper")
        self.stack_wrapper.append(self.deck_stack)

        # Overlay carries the sewn-on corner tags without affecting deck sizing
        self.cover_overlay = Gtk.Overlay()
        self.cover_overlay.set_child(self.stack_wrapper)

        self.lbl_live_tag = Gtk.Label(label="LIVE")
        self.lbl_live_tag.add_css_class("corner-tag")
        self.lbl_live_tag.add_css_class("corner-tag-left")
        self.lbl_live_tag.set_halign(Gtk.Align.START)
        self.lbl_live_tag.set_valign(Gtk.Align.START)
        self.lbl_live_tag.set_visible(False)
        self.cover_overlay.add_overlay(self.lbl_live_tag)

        self.lbl_format_tag = Gtk.Label()
        self.lbl_format_tag.add_css_class("corner-tag")
        self.lbl_format_tag.add_css_class("corner-tag-right")
        self.lbl_format_tag.set_halign(Gtk.Align.END)
        self.lbl_format_tag.set_valign(Gtk.Align.START)
        self.lbl_format_tag.set_visible(False)
        self.cover_overlay.add_overlay(self.lbl_format_tag)

        deck_box.append(self.cover_overlay)
```

- [ ] **Step 6: Show/hide the LIVE tag in `update()`**

Replace:

```python
        if not artist and not title:
            self.lbl_title.set_markup(f"<b>{html.escape(station_name)}</b>")
            self.lbl_artist.set_text("Live Stream")
            self.clear_cover()
            self._cur_artist, self._cur_title = None, None
        else:
            self.lbl_title.set_text(title or "Unknown Track")
            self.lbl_artist.set_text(artist or "Unknown Artist")
```

with:

```python
        if not artist and not title:
            self.lbl_title.set_markup(f"<b>{html.escape(station_name)}</b>")
            self.lbl_artist.set_text("Live Stream")
            self.clear_cover()
            self.lbl_live_tag.set_visible(True)
            self._cur_artist, self._cur_title = None, None
        else:
            self.lbl_title.set_text(title or "Unknown Track")
            self.lbl_artist.set_text(artist or "Unknown Artist")
            self.lbl_live_tag.set_visible(False)
```

- [ ] **Step 7: Hide both tags in `reset_ui()`**

Replace:

```python
        self.eq_strip.set_active(False)
        self.lbl_bitrate.set_visible(False)
        self.lbl_channels.set_visible(False)
        self.lbl_bt.set_visible(False)
```

with:

```python
        self.eq_strip.set_active(False)
        self.lbl_bitrate.set_visible(False)
        self.lbl_channels.set_visible(False)
        self.lbl_bt.set_visible(False)
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
```

- [ ] **Step 8: Add the `fmt` param to `update_indicators()` and render it**

Replace:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None):
```

with:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None, fmt: str | None = None):
```

Then replace:

```python
        if channels:
            self.lbl_channels.set_text("Stereo" if channels == 2 else "Mono" if channels == 1 else f"{channels}Ch")
            self.lbl_channels.set_visible(True)
        else:
            self.lbl_channels.set_visible(False)

        self.lbl_bt.set_visible(bt)
```

with:

```python
        if channels:
            self.lbl_channels.set_text("Stereo" if channels == 2 else "Mono" if channels == 1 else f"{channels}Ch")
            self.lbl_channels.set_visible(True)
        else:
            self.lbl_channels.set_visible(False)

        if fmt:
            self.lbl_format_tag.set_text(fmt)
            self.lbl_format_tag.set_visible(True)
        else:
            self.lbl_format_tag.set_visible(False)

        self.lbl_bt.set_visible(bt)
```

- [ ] **Step 9: Verify `now_playing.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 10: Thread `fmt` through `window.py`**

Replace:

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            
            GLib.idle_add(
                self._apply_daemon_state, 
                resp, icy, vol, muted, bitrate, channels
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

with:

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            fmt = daemon.get_stream_format()
            
            GLib.idle_add(
                self._apply_daemon_state, 
                resp, icy, vol, muted, bitrate, channels, fmt
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

- [ ] **Step 11: Verify `window.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/window.py').read())"
```

Expected: no output

- [ ] **Step 12: Manually verify in the running app**

Run the app and play a live stream with no ICY track metadata — the gold "LIVE" tag appears on the top-left corner of the cover art. Play a station that does send track metadata — LIVE disappears. If mpv reports a codec, the top-right corner shows it (e.g. "MP3").

- [ ] **Step 13: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py sqlch_gui/daemon.py sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py
git commit -m "feat(sqlch-gui): LIVE and format corner tags on Now Playing cover art"
```

---

## Task 4: Knob tick-stitching + fabric tags

**Files:**
- Modify: `sqlch_gui/ui/knob.py` (`RotaryKnob._on_draw`, `RecordKnob._on_draw`)
- Modify: `sqlch_gui/ui/common.py` (`.knob-tag` CSS)
- Modify: `sqlch_gui/ui/now_playing.py` (wrap `vol_knob`/`rec_knob` with VOL/REC labels)

A dashed stitch ring around each knob's bezel, plus a small fabric-tag label underneath reading VOL / REC.

- [ ] **Step 1: Add the dashed ring to `RotaryKnob._on_draw`**

In `sqlch_gui/ui/knob.py`, replace:

```python
        # Faceplate
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Unused tracking arc track
```

with:

```python
        # Faceplate
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Dashed stitch ring, echoes the fabric hem convention used elsewhere in the UI
        cr.save()
        cr.set_dash([2.0, 3.0])
        cr.set_line_width(1.5)
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.35)
        cr.arc(cx, cy, radius + 4.0, 0, 2 * math.pi)
        cr.stroke()
        cr.restore()

        # Unused tracking arc track
```

- [ ] **Step 2: Add the dashed ring to `RecordKnob._on_draw`**

Replace:

```python
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Detent dots at both switch positions
```

with:

```python
        cr.set_source_rgba(0.20, 0.20, 0.22, 1.0)
        cr.arc(cx, cy, radius - 1, 0, 2 * math.pi)
        cr.fill()

        # Dashed stitch ring, matches RotaryKnob
        cr.save()
        cr.set_dash([2.0, 3.0])
        cr.set_line_width(1.5)
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.35)
        cr.arc(cx, cy, radius + 4.0, 0, 2 * math.pi)
        cr.stroke()
        cr.restore()

        # Detent dots at both switch positions
```

- [ ] **Step 3: Verify `knob.py` syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/knob.py').read())"
```

Expected: no output

- [ ] **Step 4: Add `.knob-tag` CSS**

In `sqlch_gui/ui/common.py`, replace:

```python
    .tech-badge.rec-badge {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 1px 0 rgba({staff}, 0.60);
        outline: 1px dashed {thread_light};
    }}

    popover.context-menu > contents {{
```

with:

```python
    .tech-badge.rec-badge {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 1px 0 rgba({staff}, 0.60);
        outline: 1px dashed {thread_light};
    }}

    .knob-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.62em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.05em;
        text-shadow: 0 1px 0 {lite_c};
    }}

    popover.context-menu > contents {{
```

- [ ] **Step 5: Verify `common.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 6: Wrap `vol_knob` and `rec_knob` with VOL/REC tag labels**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.3, step_increment=0.05)

        self.vol_knob = RotaryKnob(self.vol_adj)
        self.vol_knob.set_valign(Gtk.Align.CENTER)
        self._vol_handler = self.vol_knob.connect("value-changed", self.on_vol_changed)

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.add_css_class("control-btn")
        self.btn_mute.set_valign(Gtk.Align.CENTER)
        self.btn_mute.connect("clicked", self.on_toggle_mute)

        self.rec_knob = RecordKnob()
        self.rec_knob.set_valign(Gtk.Align.CENTER)
        self.rec_knob.connect("record-toggled", self.on_record_toggled)

        hub_row.append(self.rec_knob)
        hub_row.append(btn_stop)
        hub_row.append(self.vol_knob)
        hub_row.append(self.btn_mute)
        deck.append(hub_row)
```

with:

```python
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.3, step_increment=0.05)

        self.vol_knob = RotaryKnob(self.vol_adj)
        self._vol_handler = self.vol_knob.connect("value-changed", self.on_vol_changed)

        vol_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vol_wrap.set_valign(Gtk.Align.CENTER)
        vol_wrap.set_halign(Gtk.Align.CENTER)
        vol_wrap.append(self.vol_knob)
        lbl_vol_tag = Gtk.Label(label="VOL")
        lbl_vol_tag.add_css_class("knob-tag")
        vol_wrap.append(lbl_vol_tag)

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.add_css_class("control-btn")
        self.btn_mute.set_valign(Gtk.Align.CENTER)
        self.btn_mute.connect("clicked", self.on_toggle_mute)

        self.rec_knob = RecordKnob()
        self.rec_knob.connect("record-toggled", self.on_record_toggled)

        rec_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rec_wrap.set_valign(Gtk.Align.CENTER)
        rec_wrap.set_halign(Gtk.Align.CENTER)
        rec_wrap.append(self.rec_knob)
        lbl_rec_tag = Gtk.Label(label="REC")
        lbl_rec_tag.add_css_class("knob-tag")
        rec_wrap.append(lbl_rec_tag)

        hub_row.append(rec_wrap)
        hub_row.append(btn_stop)
        hub_row.append(vol_wrap)
        hub_row.append(self.btn_mute)
        deck.append(hub_row)
```

- [ ] **Step 7: Verify `now_playing.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 8: Manually verify in the running app**

Run the app. Both knobs show a faint dashed ring around their bezel, with "VOL" and "REC" labels underneath. Confirm dragging/scrolling the volume knob still changes volume, and right-clicking the record knob still toggles FULL/TRACK mode.

- [ ] **Step 9: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/knob.py sqlch_gui/ui/common.py sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): dashed stitch ring + VOL/REC tags on control knobs"
```

---

## Task 5: Output device badge

**Files:**
- Modify: `sqlch_gui/daemon.py` (`import re`, `get_sink_name()`)
- Modify: `sqlch_gui/ui/now_playing.py` (`lbl_device` widget, `update_indicators()` param, `reset_ui()` hide)
- Modify: `sqlch_gui/ui/window.py` (thread `device_name` through the monitor loop)

The one item in this spec with real new plumbing: no existing code queries the default sink's friendly name (only volume/mute via `wpctl get-volume`). Adds a `wpctl inspect` helper and a badge in the existing tech-badge strip.

- [ ] **Step 1: Add the `re` import to `daemon.py`**

Replace:

```python
import json
import socket
import subprocess

from . import CONTROL_SOCK, MPV_SOCK
```

with:

```python
import json
import re
import socket
import subprocess

from . import CONTROL_SOCK, MPV_SOCK
```

- [ ] **Step 2: Add `get_sink_name()`**

Replace:

```python
def get_stream_format() -> str | None:
    """Return the short audio codec name (e.g. 'mp3', 'aac') from MPV, or None."""
    val = _mpv_get_property("audio-codec-name")
    if val:
        return str(val).upper()
    return None
```

with:

```python
def get_stream_format() -> str | None:
    """Return the short audio codec name (e.g. 'mp3', 'aac') from MPV, or None."""
    val = _mpv_get_property("audio-codec-name")
    if val:
        return str(val).upper()
    return None


def get_sink_name() -> str | None:
    """Return the default audio sink's friendly description from wpctl, or None."""
    try:
        r = subprocess.run(
            ["wpctl", "inspect", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        m = re.search(r'node\.description\s*=\s*"([^"]+)"', r.stdout)
        return m.group(1) if m else None
    except Exception:
        return None
```

- [ ] **Step 3: Verify `daemon.py` syntax and exercise `get_sink_name()` against the real system**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/daemon.py').read())"
python3 -c "
from sqlch_gui import daemon
name = daemon.get_sink_name()
print(repr(name))
"
```

Expected: first command prints nothing; second prints the default sink's description string (e.g. `'Family 17h/19h HD Audio Controller Analog Stereo'`), or `None` if no default sink is configured on this machine — either is fine, it confirms the function runs without raising.

- [ ] **Step 4: Add the `lbl_device` badge widget**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        self.lbl_bt = Gtk.Label(label="BT")
        self.lbl_bt.add_css_class("tech-badge")

        self.tech_box.append(self.lbl_rec)
        self.tech_box.append(self.lbl_vol_percent)
        self.tech_box.append(self.lbl_bitrate)
        self.tech_box.append(self.lbl_channels)
        self.tech_box.append(self.lbl_bt)
        deck.append(self.tech_box)
```

with:

```python
        self.lbl_bt = Gtk.Label(label="BT")
        self.lbl_bt.add_css_class("tech-badge")

        self.lbl_device = Gtk.Label()
        self.lbl_device.add_css_class("tech-badge")
        self.lbl_device.set_ellipsize(3)
        self.lbl_device.set_max_width_chars(12)
        self.lbl_device.set_visible(False)

        self.tech_box.append(self.lbl_rec)
        self.tech_box.append(self.lbl_vol_percent)
        self.tech_box.append(self.lbl_bitrate)
        self.tech_box.append(self.lbl_channels)
        self.tech_box.append(self.lbl_bt)
        self.tech_box.append(self.lbl_device)
        deck.append(self.tech_box)
```

- [ ] **Step 5: Hide the badge in `reset_ui()`**

Replace:

```python
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
```

with:

```python
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
        self.lbl_device.set_visible(False)
```

- [ ] **Step 6: Add the `device_name` param to `update_indicators()` and render it**

Replace:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None, fmt: str | None = None):
```

with:

```python
    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None, fmt: str | None = None,
                          device_name: str | None = None):
```

Then replace:

```python
        self.lbl_bt.set_visible(bt)

        rec = recording or {}
```

with:

```python
        self.lbl_bt.set_visible(bt)

        if device_name:
            self.lbl_device.set_text(device_name)
            self.lbl_device.set_visible(True)
        else:
            self.lbl_device.set_visible(False)

        rec = recording or {}
```

- [ ] **Step 7: Verify `now_playing.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 8: Thread `device_name` through `window.py`**

Replace:

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            fmt = daemon.get_stream_format()
            
            GLib.idle_add(
                self._apply_daemon_state, 
                resp, icy, vol, muted, bitrate, channels, fmt
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

with:

```python
    def _daemon_monitor_loop(self):
        import time
        from .. import metadata
        while self._keep_running:
            resp = daemon.send({"cmd": "status"})
            icy = metadata.get_icy_track()
            vol, muted = daemon.get_vol_state()
            bitrate = daemon.get_stream_bitrate()
            channels = daemon.get_stream_channels()
            fmt = daemon.get_stream_format()
            device_name = daemon.get_sink_name()
            
            GLib.idle_add(
                self._apply_daemon_state, 
                resp, icy, vol, muted, bitrate, channels, fmt, device_name
            )
            time.sleep(1.0)

    def _apply_daemon_state(self, resp, icy, vol, muted, bitrate, channels, fmt, device_name) -> bool:
        if not self._keep_running:
            return False
        self.now_playing.update(resp, icy=icy)
        playing = bool(resp and resp.get("ok") and resp.get("current"))
        recording = resp.get("recording") if resp else None
        self.now_playing.update_indicators(
            bitrate, vol, muted, self._bt_active, playing, channels,
            recording=recording, fmt=fmt, device_name=device_name,
        )
        artist, title = self.now_playing.get_current_track()
        self.station_list.set_active(self.now_playing.get_current_id(), artist, title)
        return False
```

- [ ] **Step 9: Verify `window.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/window.py').read())"
```

Expected: no output

- [ ] **Step 10: Manually verify in the running app**

Run the app and play a station. A new badge appears in the readout strip showing your current output device's name (truncated with an ellipsis if long). Switch your default output device (e.g. via `wpctl` or your system's audio menu) and confirm the badge updates within a few seconds.

- [ ] **Step 11: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/daemon.py sqlch_gui/ui/now_playing.py sqlch_gui/ui/window.py
git commit -m "feat(sqlch-gui): output device name badge on Now Playing readout strip"
```

---

## Task 6: Woven brand tag

**Files:**
- Modify: `sqlch_gui/ui/common.py` (`.brand-tag` CSS)
- Modify: `sqlch_gui/ui/now_playing.py` (wrap `deck` in an `Overlay`, add the label)

A small static "sqlch" label tucked into the bottom-right corner of the control-deck card, styled as a dashed-border sewn-in tag (no CSS pseudo-elements available in GTK, so the mockup's stitch-loop nub is dropped — the dashed border alone carries the "sewn tag" read).

- [ ] **Step 1: Add `.brand-tag` CSS**

In `sqlch_gui/ui/common.py`, replace:

```python
    .knob-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.62em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.05em;
        text-shadow: 0 1px 0 {lite_c};
    }}

    popover.context-menu > contents {{
```

with:

```python
    .knob-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.62em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.05em;
        text-shadow: 0 1px 0 {lite_c};
    }}

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

    popover.context-menu > contents {{
```

- [ ] **Step 2: Verify `common.py` syntax**

```bash
cd /home/prepko/sqlch
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/common.py').read())"
```

Expected: no output

- [ ] **Step 3: Wrap the control-deck card in an `Overlay` carrying the brand tag**

In `sqlch_gui/ui/now_playing.py`, replace:

```python
        self.tech_box.append(self.lbl_rec)
        self.tech_box.append(self.lbl_vol_percent)
        self.tech_box.append(self.lbl_bitrate)
        self.tech_box.append(self.lbl_channels)
        self.tech_box.append(self.lbl_bt)
        self.tech_box.append(self.lbl_device)
        deck.append(self.tech_box)
        self.append(deck)

        self._cur_station_id = None
```

with:

```python
        self.tech_box.append(self.lbl_rec)
        self.tech_box.append(self.lbl_vol_percent)
        self.tech_box.append(self.lbl_bitrate)
        self.tech_box.append(self.lbl_channels)
        self.tech_box.append(self.lbl_bt)
        self.tech_box.append(self.lbl_device)
        deck.append(self.tech_box)

        deck_overlay = Gtk.Overlay()
        deck_overlay.set_child(deck)
        lbl_brand = Gtk.Label(label="sqlch")
        lbl_brand.add_css_class("brand-tag")
        lbl_brand.set_halign(Gtk.Align.END)
        lbl_brand.set_valign(Gtk.Align.END)
        deck_overlay.add_overlay(lbl_brand)
        self.append(deck_overlay)

        self._cur_station_id = None
```

- [ ] **Step 4: Verify `now_playing.py` syntax**

```bash
python3 -c "import ast; ast.parse(open('sqlch_gui/ui/now_playing.py').read())"
```

Expected: no output

- [ ] **Step 5: Manually verify in the running app**

Run the app. A small dashed-border "sqlch" tag sits in the bottom-right corner of the control-deck card. Click the stop and mute buttons (which sit near that corner) to confirm the overlay label doesn't intercept clicks meant for the controls underneath.

- [ ] **Step 6: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py sqlch_gui/ui/now_playing.py
git commit -m "feat(sqlch-gui): woven brand tag on control deck"
```
