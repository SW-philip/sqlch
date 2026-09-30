"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import json
import threading
import time
from collections import deque
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf, GObject, Pango

from .. import XDG_CACHE, daemon, metadata
from .controls import VolumeMeter, RecordBubble, NavColumn
from .header import Header

_COVER_SIZE = 220     # keep in sync with .cover-art's min-width/min-height in common.py
_PREVIOUS_SLOTS = 3  # matches the history deque's maxlen
_HISTORY_TTL = 16 * 60  # seconds a previous track stays listed (~3 songs with talk)
_HISTORY_JSON = XDG_CACHE / "sqlch" / "previous-tracks.json"
_INFO_PANEL_WIDTH = 300  # fixed width for the info panel; wider than _COVER_SIZE so
                         # the Codec/Bitrate/Buffer pills fit on one line without
                         # wrapping -- the album art centers with padding to match.


class NowPlayingPanel(Gtk.Box):
    __gsignals__ = {
        'nav-selected': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

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

        # --- Row 1: header (nameplate, live plate, folder tabs) ---
        self.nav_column = NavColumn()
        self.nav_column.connect("nav-selected", lambda nav, name: self.emit("nav-selected", name))
        self.header = Header(self.nav_column, _INFO_PANEL_WIDTH)
        card.append(self.header)

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

        card.append(self.cover_overlay)

        # --- Row 3: info panel (Previous tracks) plus stream diagnostic pills ---
        # Wrapped in a non-propagating ScrolledWindow pinned to the cover
        # art's own measured width (same clip-content-not-window idiom the
        # drawer/tracklist panels already use elsewhere in this codebase),
        # so this row's width can never drive the window wider or narrower
        # as station/track text or pill visibility changes -- only the
        # fixed-size album art governs the card's width.
        info_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)

        # Always present with a fixed row count (3 single-line, ellipsized
        # slots) so the card's height never changes as history fills in.
        self.lbl_previous = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        heading = Gtk.Label(xalign=0.0)
        heading.set_markup("<b>PREVIOUS</b>")
        heading.add_css_class("info-line")
        self.lbl_previous.append(heading)
        self._prev_rows = []
        for _ in range(_PREVIOUS_SLOTS):
            row = Gtk.Label(xalign=0.0, hexpand=True)
            row.set_ellipsize(Pango.EllipsizeMode.END)
            row.set_single_line_mode(True)
            row.set_width_chars(1)
            row.set_max_width_chars(1)
            row.set_text(" ")
            row.add_css_class("info-line")
            self.lbl_previous.append(row)
            self._prev_rows.append(row)
        info_panel.append(self.lbl_previous)

        # FlowBox (not a plain Box) so pills that don't fit on one line at
        # the pinned width wrap onto a second line instead of being clipped.
        pills_row = Gtk.FlowBox()
        pills_row.set_selection_mode(Gtk.SelectionMode.NONE)
        pills_row.set_max_children_per_line(3)
        pills_row.set_row_spacing(4)
        pills_row.set_column_spacing(4)
        # Homogeneous (the default) sizes every cell to match the widest
        # pill, which can waste enough space to force an awkward 2-then-1
        # wrap even when all three would fit at their actual widths.
        pills_row.set_homogeneous(False)
        self.pill_codec = Gtk.Label()
        self.pill_codec.add_css_class("tech-badge")
        self.pill_codec.set_visible(False)
        self.pill_bitrate = Gtk.Label()
        self.pill_bitrate.add_css_class("tech-badge")
        self.pill_bitrate.set_visible(False)
        self.pill_buffer = Gtk.Label()
        self.pill_buffer.add_css_class("tech-badge")
        self.pill_buffer.set_visible(False)
        pills_row.append(self.pill_codec)
        pills_row.append(self.pill_bitrate)
        pills_row.append(self.pill_buffer)
        info_panel.append(pills_row)

        self.info_scroll = Gtk.ScrolledWindow()
        self.info_scroll.add_css_class("info-panel")
        self.info_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        self.info_scroll.set_propagate_natural_height(True)
        self.info_scroll.set_size_request(_INFO_PANEL_WIDTH, -1)
        self.info_scroll.set_child(info_panel)
        # A touch more than the card's uniform row spacing -- the art's
        # matted frame/cutout shadow reads as visually heavier than the
        # nav row above it, so the plain 4px spacing looked tighter here
        # than the gap up top.
        self.info_scroll.set_margin_top(4)
        card.append(self.info_scroll)

        # --- Row 4: RecordBubble / stop-play toggle | speaker + volume meter ---
        control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.rec_bubble = RecordBubble()
        self.rec_bubble.connect("record-toggled", self.on_record_clicked)
        control_row.append(self.rec_bubble)

        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.add_css_class("primary")
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        control_row.append(self.btn_toggle)

        control_row.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self.speaker_icon = Gtk.Image(icon_name="audio-volume-high-symbolic")
        self.speaker_icon.set_valign(Gtk.Align.CENTER)
        control_row.append(self.speaker_icon)

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)
        self.vol_meter = VolumeMeter(self.vol_adj)
        self._vol_handler = self.vol_meter.connect("value-changed", self.on_vol_changed)
        self._pre_boost_vol: float | None = None
        self.vol_meter.connect("boost-toggled", self.on_boost_toggled)
        self.vol_meter.set_hexpand(True)
        control_row.append(self.vol_meter)

        card.append(control_row)

        self.append(card)

        self._cur_station_id = None
        self._cur_frequency = None
        self._cur_artist = None
        self._cur_title = None
        self._live_station_name = None
        # (artist, title, time it stopped playing), newest first
        self._history: deque[tuple[str, str, float]] = deque(maxlen=_PREVIOUS_SLOTS)
        self._hist_station_id = None  # station the history belongs to
        self._loaded = False
        self.reset_ui()
        self._load_history()

    def clear_cover(self):
        self.cover_stack.set_visible_child_name("placeholder")

    def _set_stale(self, stale: bool):
        """Dim the info panel and cover art while stopped, without touching
        their content -- the idle card keeps showing the last-known station
        and track instead of collapsing to blank."""
        for widget in (self.info_scroll, self.cover_stack):
            if stale:
                widget.add_css_class("stale")
            else:
                widget.remove_css_class("stale")
        self.header.set_stale(stale)

    def set_connected(self, connected: bool):
        self.header.set_connected(connected)

    def _set_pills_placeholder(self):
        self.pill_codec.set_text("Codec: --")
        self.pill_codec.set_visible(True)
        self.pill_bitrate.set_text("Bitrate: --")
        self.pill_bitrate.set_visible(True)
        self.pill_buffer.set_text("Buffer: --")
        self.pill_buffer.set_visible(True)

    def reset_ui(self):
        """Initial, never-played state -- same dimmed/idle look as stopping
        after a station has played, just with placeholder text instead of
        last-known station/track."""
        self.header.set_station("<b>STATION</b>  —")
        self.header.set_track("<i>Not Playing</i>")
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.lbl_live_tag.set_visible(False)
        self._set_pills_placeholder()
        self.rec_bubble.set_state(False, "full")
        self.clear_cover()
        self._set_stale(True)
        self._cur_station_id = None
        self._cur_frequency = None
        self._cur_artist = None
        self._cur_title = None
        self._live_station_name = None
        self._history.clear()
        self._hist_station_id = None
        self._render_previous()

    def _load_history(self):
        """Restore the previous-tracks list saved by an earlier run, so
        closing and reopening the window doesn't wipe it."""
        try:
            data = json.loads(_HISTORY_JSON.read_text())
            entries = [(a, t, float(ts)) for a, t, ts in data["history"]]
            cur = data.get("current")
            saved_at = float(data["saved_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return
        self._hist_station_id = data.get("station")
        self._history.extend(entries[:_PREVIOUS_SLOTS])
        # Resume the track that was playing at close, so it is pushed into
        # history if a new one has started since.
        if cur and time.time() - saved_at < _HISTORY_TTL:
            self._cur_artist, self._cur_title = cur
        self._prune_history()
        self._render_previous()

    def _save_history(self):
        try:
            _HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
            _HISTORY_JSON.write_text(json.dumps({
                "station": self._hist_station_id,
                "saved_at": time.time(),
                "current": [self._cur_artist, self._cur_title] if self._cur_artist and self._cur_title else None,
                "history": [list(e) for e in self._history],
            }))
        except OSError:
            pass

    def _prune_history(self):
        cutoff = time.time() - _HISTORY_TTL
        while self._history and self._history[-1][2] < cutoff:
            self._history.pop()

    def get_current_id(self) -> str | None:
        return self._cur_station_id

    def get_current_track(self) -> tuple[str | None, str | None]:
        return self._cur_artist, self._cur_title

    def _update_station_line(self):
        freq_txt = f"{self._cur_frequency:.1f} FM · " if self._cur_frequency else ""
        genre = metadata.get_icy_genre()
        if not genre and self._cur_artist and self._cur_title:
            meta = metadata.get_enriched_meta(self._cur_artist, self._cur_title)
            if meta and meta.get("genres"):
                genre = meta["genres"][0]
        suffix = f" · {html.escape(genre)}" if genre else ""
        name = html.escape(self._live_station_name or "Unknown Station")
        self.header.set_station(f"<b>STATION</b>  {freq_txt}{name}{suffix}")

    def _update_previous_line(self):
        self._render_previous()

    def _render_previous(self):
        self._prune_history()
        for i, row in enumerate(self._prev_rows):
            if i < len(self._history):
                a, t, _ = self._history[i]
                row.set_text(f"{i + 1}. {a} — {t}")
            elif i == 0 and self._cur_station_id is not None:
                row.set_text("It's playing now")
            else:
                row.set_text(" ")  # empty text collapses the row; a space keeps its height

    def update(self, resp: dict | None, icy: tuple[str | None, str | None]):
        if not resp or not resp.get("ok") or not resp.get("current"):
            # Stopped: leave the last-rendered station/track/previous/cover
            # in place (dimmed via _set_stale) instead of wiping them --
            # only the LIVE tag is no longer accurate and gets hidden.
            self._set_stale(True)
            self.lbl_live_tag.set_visible(False)
            return

        self._set_stale(False)
        curr = resp["current"]
        # resp["current"] is {"type": "station", "item": station}, not a
        # flat station dict -- id/name/frequency live under "item".
        item = curr.get("item") or {}
        station_id = item.get("id")
        station_name = item.get("name") or "Unknown Station"
        frequency = item.get("frequency")

        if station_id != self._hist_station_id:
            self._history.clear()
            self._cur_artist, self._cur_title = None, None
            self._hist_station_id = station_id

        self._cur_station_id = station_id
        self._cur_frequency = frequency
        self._live_station_name = station_name

        raw_artist, raw_title = icy
        artist = raw_artist.strip() if raw_artist else ""
        title = raw_title.strip() if raw_title else ""

        if not artist and not title:
            self.clear_cover()
            self.lbl_live_tag.set_visible(True)
            self.header.set_track("<i>Live Stream</i>")
            self._cur_artist, self._cur_title = None, None
        else:
            self.lbl_live_tag.set_visible(False)
            display_artist = artist or "Unknown Artist"
            display_title = title or "Unknown Track"
            self.header.set_track(
                f"<b>{html.escape(display_artist)} — {html.escape(display_title)}</b>"
            )

            if artist != self._cur_artist or title != self._cur_title:
                # Half-filled metadata (title only, e.g. a raw stream id) is
                # pre-tag junk from the player, not a track worth remembering.
                if self._cur_artist and self._cur_title:
                    self._history.appendleft((self._cur_artist, self._cur_title, time.time()))
                self._cur_artist = artist
                self._cur_title = title
                self._save_history()
                metadata.run_enrich(artist, title)
                threading.Thread(target=self._async_fetch_cover, args=(artist, title), daemon=True).start()

        self._update_station_line()
        self._update_previous_line()

    def _async_fetch_cover(self, artist: str, title: str):
        import time
        time.sleep(3.0)  # give sqlch-enrich time to write enriched.json
        if self._cur_artist != artist or self._cur_title != title:
            return  # track already changed, bail
        path, mode = metadata.get_cover_info(artist, title)
        if mode == "remote" and path:
            import hashlib
            h = hashlib.md5(f"{artist.lower()}|{title.lower()}".encode()).hexdigest()
            local_path = metadata.COVERS_DIR / f"{h}.jpg"
            if metadata.download_cover(path, local_path):
                path = str(local_path)
                mode = "local"

        if mode == "local" and path and Path(path).exists():
            GLib.idle_add(self._apply_cover_path, path, artist, title)

    def _apply_cover_path(self, path: str, artist: str, title: str) -> bool:
        if self._cur_artist == artist and self._cur_title == title:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, _COVER_SIZE, _COVER_SIZE, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
        return False

    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, playing: bool,
                          recording: dict | None = None, fmt: str | None = None,
                          buffer: int | None = None):
        self._loaded = playing
        self.btn_toggle.set_icon_name("media-playback-stop-symbolic" if playing else "media-playback-start-symbolic")

        # Block signals temporarily to prevent loopback configuration cascades
        self.vol_meter.handler_block(self._vol_handler)
        self.vol_adj.set_value(vol)
        self.vol_meter.handler_unblock(self._vol_handler)

        if muted:
            self.speaker_icon.set_from_icon_name("audio-volume-muted-symbolic")
        elif vol < 0.4:
            self.speaker_icon.set_from_icon_name("audio-volume-low-symbolic")
        elif vol < 0.8:
            self.speaker_icon.set_from_icon_name("audio-volume-medium-symbolic")
        else:
            self.speaker_icon.set_from_icon_name("audio-volume-high-symbolic")

        if not playing:
            self._set_pills_placeholder()
        else:
            if fmt:
                self.pill_codec.set_text(f"Codec: {fmt}")
                self.pill_codec.set_visible(True)
            else:
                self.pill_codec.set_visible(False)

            if bitrate:
                self.pill_bitrate.set_text(f"Bitrate: {bitrate}k")
                self.pill_bitrate.set_visible(True)
            else:
                self.pill_bitrate.set_visible(False)

            if buffer is not None:
                self.pill_buffer.set_text(f"Buffer: {buffer}%")
                self.pill_buffer.set_visible(True)
            else:
                self.pill_buffer.set_visible(False)

        rec = recording or {}
        mode = rec.get("mode")
        if mode not in ("full", "track"):
            mode = self.rec_bubble.mode
        self.rec_bubble.set_state(bool(rec.get("active")), mode)

    def on_record_clicked(self, bubble, mode):
        daemon.send({"cmd": "record", "action": "toggle", "mode": mode})

    def on_toggle_play(self, btn):
        if self._loaded:
            daemon.send({"cmd": "stop"})
        else:
            daemon.send({"cmd": "play", "query": "__last__"})

    def on_vol_changed(self, meter, val):
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)

    def on_boost_toggled(self, meter, active):
        import subprocess
        if active:
            self._pre_boost_vol = self.vol_adj.get_value()
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.20"], stdout=subprocess.DEVNULL)
        else:
            restore = self._pre_boost_vol if self._pre_boost_vol is not None else 0.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{restore:.2f}"], stdout=subprocess.DEVNULL)
            self._pre_boost_vol = None
