# Now Playing Stacked Deck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace sqlch_gui's Now Playing cover-art/tracklist flip-card with a stacked layout where both are simultaneously visible, per `docs/superpowers/specs/2026-07-29-now-playing-stacked-deck-design.md`.

**Architecture:** All changes live in two files: `sqlch_gui/ui/common.py` (CSS — resize `.cover-art`, drop the rotating wrapper and flip-tag classes, rename the back-panel class) and `sqlch_gui/ui/now_playing.py` (the layout rewrite: art becomes its own full-width row, text moves below it, tracklist becomes a permanent full-width row instead of the flip-card's back face). No test infrastructure exists in this repo (a GTK4/Wayland popup with Cairo-drawn widgets isn't practically unit-tested); every task ends with a manual verification step against a live dev instance instead of an automated test run, consistent with `2026-07-25-now-playing-merged-deck.md` and other prior plans in this repo.

**Tech Stack:** Python 3, GTK4 (PyGObject), Gtk4LayerShell, Cairo (via PyGObject's `cairo` bindings).

---

## Dev instance launch (used by every verification step below)

```bash
pkill -f "python3 -m sqlch_gui"
```

Then, in a separate command, read the installed wrapper for current env vars (the nix store hash changes on rebuild, so re-read each time) and launch the working tree with `/home/prepko/sqlch` first in `PYTHONPATH`:

```bash
head -30 /etc/profiles/per-user/prepko/bin/sqlch-gui
# copy the export lines (especially LD_PRELOAD=.../libgtk4-layer-shell.so), then:
PYTHONPATH=/home/prepko/sqlch:$PYTHONPATH LD_PRELOAD=<path-from-wrapper> python3 -m sqlch_gui
```

A clean launch has no layer-shell warnings in its output; `VK_SUBOPTIMAL` Gdk warnings are benign noise. Kill the instance (by PID, separate command) once each verification step is done — don't leave dev instances running between tasks.

---

### Task 1: Resize and clean up CSS in common.py

**Files:**
- Modify: `sqlch_gui/ui/common.py:111-117` (`.cover-art`)
- Modify: `sqlch_gui/ui/common.py:466-485` (`.album-deck-wrapper`, `.art-card-back`)
- Modify: `sqlch_gui/ui/common.py:497-519` (`.corner-tag-flip`)

- [ ] **Step 1: Bump `.cover-art` to the new size**

Replace (lines 111-117):

```python
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        min-width: 98px;
        min-height: 98px;
        box-shadow: {slight};
    }}
```

with:

```python
    /* Size kept in sync with _COVER_SIZE in now_playing.py */
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        min-width: 220px;
        min-height: 220px;
        box-shadow: {slight};
    }}
```

- [ ] **Step 2: Remove the rotating wrapper, rename the back-panel class**

Replace (lines 466-485):

```python
    /* Album Deck Outer Container - baseline rotation state */
    .album-deck-wrapper {{
        border-radius: 12px;
        transition: transform 250ms cubic-bezier(0.4, 0.0, 0.2, 1);
        transform: rotate(-3deg);
    }}

    /* Subtle geometric physics push when flipped open */
    .album-deck-wrapper.flipped {{
        transform: rotate(2deg) scale(1.02);
    }}

    /* Back side styling - Looks like a typewriter ledger scrap pasted to cardboard */
    .art-card-back {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border-radius: 12px;
        border: 2px solid {outline};
        box-shadow: inset 0 0 4px rgba({staff}, 0.15), {cutout(3, 3)}, {slight};
        padding: 6px;
    }}
```

with:

```python
    /* Tracklist panel - permanent full-width row below the meta text,
       no longer a flip-card back face. Looks like a typewriter ledger
       scrap pasted to cardboard. */
    .tracklist-panel {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border-radius: 12px;
        border: 2px solid {outline};
        box-shadow: inset 0 0 4px rgba({staff}, 0.15), {cutout(3, 3)}, {slight};
        padding: 6px;
    }}
```

- [ ] **Step 3: Remove `.corner-tag-flip`**

Delete (lines 497-519):

```python
    /* Flip corner glyph - a small clickable tag tucked into the art's own
       bottom-right corner, same rotation family as corner-tag-right
       (used by the top-right format tag) since both sit on the right. */
    .corner-tag-flip {{
        background-color: {colors.get('BAR', '#6a6a6a')};
        color: {score};
        border: 2px solid {outline};
        border-radius: 8px;
        padding: 3px 5px;
        min-height: 0;
        min-width: 0;
        margin: 5px;
        box-shadow: {cutout(2, 2)};
        transform: rotate(4deg);
        transition: transform 120ms ease, background-color 120ms ease;
    }}
    .corner-tag-flip:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        transform: rotate(4deg) scale(1.1);
    }}
    .corner-tag-flip:active {{
        transform: rotate(4deg) scale(0.92);
    }}
```

Leave the trailing `"""` (end of the `css` f-string) and everything after it untouched.

- [ ] **Step 4: Verify manually**

Launch the dev instance (see launch section above). Confirm the app starts without CSS parse errors or GTK warnings about unknown properties (check terminal output). The card will look unchanged for now — `now_playing.py` still references the old class names and widget sizes until Task 2, so this step is only checking that the CSS itself is valid.

Kill the dev instance.

- [ ] **Step 5: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/common.py
git commit -m "$(cat <<'EOF'
style(sqlch-gui): resize cover-art and retire flip-card CSS

Bumps .cover-art from 98px to 220px, drops the rotating
.album-deck-wrapper and .corner-tag-flip classes (no more flip
interaction), and renames .art-card-back to .tracklist-panel now that
it's a permanent panel instead of a flip-card back face. Per the
stacked-deck redesign spec.
EOF
)"
```

---

### Task 2: Restructure NowPlayingPanel into the stacked layout

**Files:**
- Modify: `sqlch_gui/ui/now_playing.py` (imports/constants, `__init__`, `reset_ui`, `_sync_back_plate` → `_sync_tracklist`, `update`, `_apply_cover_path`; delete `on_flip_clicked`)

This is the task that ties Task 1's CSS changes together and actually changes what the card looks like and how it behaves. It's one coherent rewrite of `NowPlayingPanel`, done in ordered steps so intermediate states stay syntactically valid, but only the final verification step (launching the app and playing a station) proves it actually works end to end -- there's no way to test GTK layout/data-flow code without running it. Everything here lands in a single commit at the end, since a commit partway through (e.g. after only the `__init__` rewrite) would leave `update()` calling `self.deck_stack`, which no longer exists.

- [ ] **Step 1: Add the size constants**

Replace lines 1-12:

```python
"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf, GObject

from .. import daemon, metadata
from .controls import ThreadSlider, NavColumn
from .eq_strip import EqStrip

_REC_MODE_LABELS = {"full": "F", "track": "T"}
```

with:

```python
"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf, GObject

from .. import daemon, metadata
from .controls import ThreadSlider, NavColumn
from .eq_strip import EqStrip

_REC_MODE_LABELS = {"full": "F", "track": "T"}
_COVER_SIZE = 220     # keep in sync with .cover-art's min-width/min-height in common.py
_TRACKLIST_HEIGHT = 130  # ~5-6 track rows before scrolling
```

- [ ] **Step 2: Rewrite `__init__`**

Replace the entire `__init__` method (from `def __init__(self, parent_window):` through the line before `def clear_cover(self):`, i.e. lines 19-216) with:

```python
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.set_margin_start(3)
        self.set_margin_end(3)
        self.set_margin_top(3)
        self.set_margin_bottom(3)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.add_css_class("card")

        # --- Row 1: nav row + plain-text readout ---
        nav_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        self.nav_column = NavColumn()
        self.nav_column.connect("nav-selected", lambda nav, name: self.emit("nav-selected", name))
        nav_row.append(self.nav_column)

        self.lbl_readout = Gtk.Label(xalign=1.0)
        self.lbl_readout.add_css_class("readout-line")
        self.lbl_readout.set_hexpand(True)
        self.lbl_readout.set_halign(Gtk.Align.END)
        nav_row.append(self.lbl_readout)

        card.append(nav_row)

        # --- Row 2: album art, full card width, corner tags overlaid ---
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(_COVER_SIZE)
        self.cover_placeholder = Gtk.Label(label="♪")
        self.cover_placeholder.add_css_class("cover-glyph")

        self.cover_stack = Gtk.Stack()
        self.cover_stack.add_css_class("cover-art")
        self.cover_stack.add_named(self.cover_placeholder, "placeholder")
        self.cover_stack.add_named(self.cover_img, "art")
        self.clear_cover()

        self.cover_overlay = Gtk.Overlay()
        self.cover_overlay.set_child(self.cover_stack)
        self.cover_overlay.set_halign(Gtk.Align.CENTER)

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

        # REC corner tag (bottom-left). Plain text tag from the same
        # .corner-tag family as LIVE/format; left-click toggles
        # recording, right-click cycles FULL/TRACK mode.
        self.rec_tag = Gtk.Button(label="REC")
        self.rec_tag.add_css_class("corner-tag")
        self.rec_tag.add_css_class("corner-tag-rec")
        self.rec_tag.set_halign(Gtk.Align.START)
        self.rec_tag.set_valign(Gtk.Align.END)
        self.rec_tag.connect("clicked", self.on_record_clicked)
        rec_right_click = Gtk.GestureClick.new()
        rec_right_click.set_button(3)
        rec_right_click.connect("released", self.on_rec_mode_cycle)
        self.rec_tag.add_controller(rec_right_click)
        self.cover_overlay.add_overlay(self.rec_tag)

        card.append(self.cover_overlay)

        # --- Row 3: title/artist/genre text, full width, EQ strip behind it ---
        # The Overlay sizes to its main child (eq_strip) by default, which
        # would clip the text block -- set_measure_overlay tells it to
        # also account for the text_box overlay child's own size. eq_strip
        # is halign FILL (rather than the old narrow-column START) so the
        # decorative bead strip stretches across the row's new full width.
        self.eq_strip = EqStrip()
        self.eq_strip.set_halign(Gtk.Align.FILL)
        self.eq_strip.set_valign(Gtk.Align.CENTER)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_halign(Gtk.Align.START)
        text_box.set_valign(Gtk.Align.CENTER)
        self.lbl_title = Gtk.Label(xalign=0.0, justify=Gtk.Justification.LEFT)
        self.lbl_title.add_css_class("meta-title")
        self.lbl_title.set_wrap(True)
        self.lbl_title.set_max_width_chars(22)

        self.lbl_artist = Gtk.Label(xalign=0.0, justify=Gtk.Justification.LEFT)
        self.lbl_artist.add_css_class("meta-artist")
        self.lbl_artist.set_wrap(True)
        self.lbl_artist.set_max_width_chars(22)

        self.lbl_genre = Gtk.Label(xalign=0.0, justify=Gtk.Justification.LEFT)
        self.lbl_genre.add_css_class("thread-label")

        text_box.append(self.lbl_title)
        text_box.append(self.lbl_artist)
        text_box.append(self.lbl_genre)

        text_overlay = Gtk.Overlay()
        text_overlay.set_child(self.eq_strip)
        text_overlay.add_overlay(text_box)
        text_overlay.set_measure_overlay(text_box, True)
        text_overlay.set_hexpand(True)
        card.append(text_overlay)

        # --- Row 4: tracklist, permanently visible, scrolls past ~5-6 rows ---
        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(-1, _TRACKLIST_HEIGHT)
        track_scroll.set_hexpand(True)
        track_scroll.add_css_class("tracklist-panel")

        self.track_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.track_list_box.add_css_class("tracklist-container")
        track_scroll.set_child(self.track_list_box)
        card.append(track_scroll)

        # --- Row 5: Stop / Volume / Mute / Play, one merged control row ---
        control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("control-btn")
        btn_stop.connect("clicked", self.on_stop)
        control_row.append(btn_stop)

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)
        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
        self._pre_boost_vol: float | None = None
        self.vol_slider.connect("boost-toggled", self.on_boost_toggled)
        self.vol_slider.set_hexpand(True)
        control_row.append(self.vol_slider)

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.add_css_class("control-btn")
        self.btn_mute.connect("clicked", self.on_toggle_mute)
        control_row.append(self.btn_mute)

        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.add_css_class("primary")
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        control_row.append(self.btn_toggle)

        card.append(control_row)

        card_overlay = Gtk.Overlay()
        card_overlay.set_child(card)
        lbl_brand = Gtk.Label(label="sqlch")
        lbl_brand.add_css_class("brand-tag")
        lbl_brand.set_halign(Gtk.Align.END)
        lbl_brand.set_valign(Gtk.Align.START)
        # Purely decorative: a bare Gtk.Label added via Gtk.Overlay.add_overlay()
        # does NOT click-through by default (Gtk.Widget.pick() resolves to the
        # topmost can_target widget at a point, regardless of whether it has any
        # click handling), so explicitly opt this label out of hit-testing to
        # guarantee stop/mute/knob clicks below always reach their real targets.
        lbl_brand.set_can_target(False)
        card_overlay.add_overlay(lbl_brand)
        self.append(card_overlay)

        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None
        self._loaded = False
        self._vol = 0.0
        self._bitrate = None
        self._channels = None
        self._bt = False
        self._device_name = None
        self._rec_mode = "full"
        self._rec_active = False
        self._rec_elapsed = 0
        self.reset_ui()
```

- [ ] **Step 3: Fix `reset_ui`**

Replace:

```python
        # Sync back-plate layout status
        self.stack_wrapper.remove_css_class("flipped")
        self.deck_stack.set_visible_child_name("front")
```

(the last three lines of `reset_ui`) with:

```python
        self._sync_tracklist()
```

- [ ] **Step 4: Rename `_sync_back_plate` to `_sync_tracklist` and widen the text wrap**

Replace the whole method:

```python
    def _sync_back_plate(self):
        """Populates the back-plate with the real album tracklist or drops back to fallback view."""
        while child := self.track_list_box.get_first_child():
            self.track_list_box.remove(child)

        meta = None
        if self._cur_artist and self._cur_title:
            meta = metadata.get_enriched_meta(self._cur_artist, self._cur_title)

        if meta and meta.get("tracklist"):
            # Header tracklist render
            album_lbl = Gtk.Label(xalign=0.0)
            album_lbl.set_markup(f"<b>{html.escape(meta.get('album') or 'Unknown Album')}</b>")
            album_lbl.set_wrap(True)
            album_lbl.set_max_width_chars(14)
            self.track_list_box.append(album_lbl)

            # Individual track matrix layout injection
            canonical_track = meta.get("track", "")
            for track_item in meta["tracklist"]:
                num = track_item.get("number", 0)
                name = track_item.get("name", "")

                track_lbl = Gtk.Label(xalign=0.0)
                escaped_name = html.escape(name)

                if name == canonical_track:
                    track_lbl.set_markup(f"<b>{num}. {escaped_name}</b>")
                else:
                    track_lbl.set_markup(f"{num}. {escaped_name}")

                track_lbl.set_wrap(True)
                track_lbl.set_max_width_chars(14)
                self.track_list_box.append(track_lbl)
        else:
            # Fallback rendering view
            lbl_info = Gtk.Label(xalign=0.0)
            lbl_info.set_markup(f"<b>A面:</b>\n{html.escape(self._cur_title or 'No Track')}\n\n<i>{html.escape(self._cur_artist or 'Unknown Artist')}</i>")
            lbl_info.set_wrap(True)
            lbl_info.set_max_width_chars(14)
            self.track_list_box.append(lbl_info)
```

with:

```python
    def _sync_tracklist(self):
        """Populates the always-visible tracklist panel with the real album
        tracklist, or drops back to a fallback view when none is cached yet."""
        while child := self.track_list_box.get_first_child():
            self.track_list_box.remove(child)

        meta = None
        if self._cur_artist and self._cur_title:
            meta = metadata.get_enriched_meta(self._cur_artist, self._cur_title)

        if meta and meta.get("tracklist"):
            # Header tracklist render
            album_lbl = Gtk.Label(xalign=0.0)
            album_lbl.set_markup(f"<b>{html.escape(meta.get('album') or 'Unknown Album')}</b>")
            album_lbl.set_wrap(True)
            album_lbl.set_max_width_chars(30)
            self.track_list_box.append(album_lbl)

            # Individual track matrix layout injection
            canonical_track = meta.get("track", "")
            for track_item in meta["tracklist"]:
                num = track_item.get("number", 0)
                name = track_item.get("name", "")

                track_lbl = Gtk.Label(xalign=0.0)
                escaped_name = html.escape(name)

                if name == canonical_track:
                    track_lbl.set_markup(f"<b>{num}. {escaped_name}</b>")
                else:
                    track_lbl.set_markup(f"{num}. {escaped_name}")

                track_lbl.set_wrap(True)
                track_lbl.set_max_width_chars(30)
                self.track_list_box.append(track_lbl)
        else:
            # Fallback rendering view
            lbl_info = Gtk.Label(xalign=0.0)
            lbl_info.set_markup(f"<b>A面:</b>\n{html.escape(self._cur_title or 'No Track')}\n\n<i>{html.escape(self._cur_artist or 'Unknown Artist')}</i>")
            lbl_info.set_wrap(True)
            lbl_info.set_max_width_chars(30)
            self.track_list_box.append(lbl_info)
```

(The `max_width_chars` bump from 14 to 30 matches the panel's new full-card width instead of the old 98px column — tune live if album names still wrap awkwardly.)

- [ ] **Step 5: Delete `on_flip_clicked`**

Delete this method entirely:

```python
    def on_flip_clicked(self, btn):
        current = self.deck_stack.get_visible_child_name()
        if current == "front":
            self.stack_wrapper.add_css_class("flipped")
            self.deck_stack.set_visible_child_name("back")
            self._sync_back_plate()
        else:
            self.stack_wrapper.remove_css_class("flipped")
            self.deck_stack.set_visible_child_name("front")
```

- [ ] **Step 6: Rewrite `update` to always keep the tracklist in sync**

Replace the `update` method:

```python
    def update(self, resp: dict | None, icy: tuple[str | None, str | None]):
        if not resp or not resp.get("ok") or not resp.get("current"):
            self.reset_ui()
            return

        curr = resp["current"]
        self._cur_station_id = curr.get("id")
        station_name = curr.get("name", "Unknown Station")

        raw_artist, raw_title = icy
        artist = raw_artist.strip() if raw_artist else ""
        title = raw_title.strip() if raw_title else ""

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

            if artist != self._cur_artist or title != self._cur_title:
                self._cur_artist = artist
                self._cur_title = title
                metadata.run_enrich(artist, title)
                threading.Thread(target=self._async_fetch_cover, args=(artist, title), daemon=True).start()

        # Push real-time updates directly to the back ledger if open
        if self.deck_stack.get_visible_child_name() == "back":
            self._sync_back_plate()

        genre = metadata.get_icy_genre()
        if not genre and self._cur_artist and self._cur_title:
            meta = metadata.get_enriched_meta(self._cur_artist, self._cur_title)
            if meta and meta.get("genres"):
                genre = meta["genres"][0]
        self._set_genre(genre)
```

with:

```python
    def update(self, resp: dict | None, icy: tuple[str | None, str | None]):
        if not resp or not resp.get("ok") or not resp.get("current"):
            self.reset_ui()
            return

        curr = resp["current"]
        self._cur_station_id = curr.get("id")
        station_name = curr.get("name", "Unknown Station")

        raw_artist, raw_title = icy
        artist = raw_artist.strip() if raw_artist else ""
        title = raw_title.strip() if raw_title else ""

        prev_artist, prev_title = self._cur_artist, self._cur_title

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

            if artist != self._cur_artist or title != self._cur_title:
                self._cur_artist = artist
                self._cur_title = title
                metadata.run_enrich(artist, title)
                threading.Thread(target=self._async_fetch_cover, args=(artist, title), daemon=True).start()
                threading.Thread(target=self._async_resync_tracklist, args=(artist, title), daemon=True).start()

        # The tracklist is always visible now (no flip gate) -- rebuild it
        # once whenever the track actually changed, rather than on every
        # 1s daemon poll tick regardless of whether anything changed.
        if (self._cur_artist, self._cur_title) != (prev_artist, prev_title):
            self._sync_tracklist()

        genre = metadata.get_icy_genre()
        if not genre and self._cur_artist and self._cur_title:
            meta = metadata.get_enriched_meta(self._cur_artist, self._cur_title)
            if meta and meta.get("genres"):
                genre = meta["genres"][0]
        self._set_genre(genre)
```

- [ ] **Step 7: Add `_async_resync_tracklist`, mirroring `_async_fetch_cover`'s enrichment-wait pattern**

Insert this new method directly after `_async_fetch_cover` (which ends right before `_apply_cover_path`):

```python
    def _async_resync_tracklist(self, artist: str, title: str):
        import time
        time.sleep(3.0)  # give sqlch-enrich time to write enriched.json
        if self._cur_artist != artist or self._cur_title != title:
            return  # track already changed, bail
        GLib.idle_add(self._sync_tracklist)
```

- [ ] **Step 8: Fix `_apply_cover_path`'s hardcoded pixel size**

Replace:

```python
    def _apply_cover_path(self, path: str, artist: str, title: str) -> bool:
        if self._cur_artist == artist and self._cur_title == title:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 98, 98, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
        return False
```

with:

```python
    def _apply_cover_path(self, path: str, artist: str, title: str) -> bool:
        if self._cur_artist == artist and self._cur_title == title:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, _COVER_SIZE, _COVER_SIZE, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
        return False
```

- [ ] **Step 9: Sanity-check the whole file for leftover flip-card references**

```bash
cd /home/prepko/sqlch
grep -n "deck_stack\|stack_wrapper\|flip_btn\|art_text_row\|_sync_back_plate\|on_flip_clicked\|corner-tag-flip\|album-deck-wrapper\|art-card-back" sqlch_gui/ui/now_playing.py sqlch_gui/ui/common.py
```

Expected: no output. If anything shows up, it's a leftover reference Tasks 1-3 should have replaced — fix it before continuing.

- [ ] **Step 10: Verify manually against the full spec testing checklist**

Launch the dev instance. Play a station with enriched metadata available and confirm:
1. Album art renders large and square at the top, LIVE/format/REC corner tags positioned correctly and clickable, no flip button anywhere.
2. Title/artist/genre text renders below the art, EQ strip animating behind it (now stretched full-width) while playing, inert while stopped.
3. Tracklist renders below the text, always visible, showing ~5-6 rows before scrolling, current track bolded, album name wrapping legibly at the new width (not artificially narrow).
4. Change tracks (or switch stations): tracklist updates immediately with whatever's cached (or the fallback view), then updates again a few seconds later once enrichment lands if it wasn't cached yet.
5. Stop playback: card resets to "Not Playing", tracklist panel clears back to its fallback view (no stale track list left over from the last station).
6. No flip button/interaction remains anywhere on the art; no console errors/warnings referencing removed attributes.
7. The popup window grows taller (not wider) to fit the new layout, still anchored top+right; the seam-drag drawer (Library/Discover) still opens/closes/animates correctly to the left of the now-taller Now Playing card.
8. Switch through at least two `palette.sh` themes and confirm `.cover-art` and `.tracklist-panel` still read correctly (background, border, shadow) in both.

Kill the dev instance.

- [ ] **Step 11: Commit**

```bash
cd /home/prepko/sqlch
git add sqlch_gui/ui/now_playing.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): replace flip-card with a stacked Now Playing layout

Album art becomes its own full-width row (220px, no rotation, no flip
button); title/artist/genre text moves below it instead of beside it;
the tracklist becomes a permanent full-width panel instead of the
flip-card's back face, rebuilding whenever the track actually changes
plus a delayed re-sync mirroring the cover-art fetch's enrichment-wait
pattern. Implements the stacked-deck redesign spec.
EOF
)"
```

---

### Task 3: Final cross-theme QA pass

**Files:** none (verification only)

- [ ] **Step 1: Full walkthrough**

Launch the dev instance. Re-run the design spec's full testing checklist end to end in one sitting (not per-task in isolation this time):

1. Library and Discover panels are visually unchanged (confirms no accidental CSS bleed from `.cover-art`/`.tracklist-panel` changes, since neither class is used there).
2. Switch through at least two `palette.sh` themes and re-check the art, text row, tracklist panel, and corner tags in each.
3. Resize/reopen the popup a few times (mini <-> library <-> discover <-> mini) to confirm the seam-drag drawer's spring-snap animation still feels unchanged against the now-taller Now Playing card (this pass didn't touch `window.py`, but the drawer's height now pins to a taller sibling).
4. Play several different stations/tracks in a row (including at least one where enrichment is slow/unavailable) to confirm the tracklist panel never shows stale data from a previous track and the fallback view reads correctly when no tracklist exists.

- [ ] **Step 2: Report results**

If everything passes, the redesign is complete. If anything's off (spacing, wrapping, a missed reference, `_TRACKLIST_HEIGHT`/`_COVER_SIZE` feeling too big or small in practice), fix inline and re-verify rather than opening a new task — this is polish on already-committed work, not new scope.
