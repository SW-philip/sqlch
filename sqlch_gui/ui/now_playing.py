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


def _fmt_duration(ms: int | None) -> str | None:
    if not ms:
        return None
    total_s = ms // 1000
    return f"{total_s // 60}:{total_s % 60:02d}"

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

        # Title/artist/genre caption, docked to the art's bottom edge over a
        # translucent scrim (see .art-caption) so it reads regardless of the
        # art's own colors.
        caption_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        caption_box.add_css_class("art-caption")
        caption_box.set_halign(Gtk.Align.FILL)
        caption_box.set_valign(Gtk.Align.END)

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

        caption_box.append(self.lbl_title)
        caption_box.append(self.lbl_artist)
        caption_box.append(self.lbl_genre)
        self.cover_overlay.add_overlay(caption_box)

        # REC corner tag (bottom-right). Added last so it floats on top of
        # the caption scrim rather than being covered by it. Plain text tag
        # from the same .corner-tag family as LIVE/format; left-click
        # toggles recording, right-click cycles FULL/TRACK mode.
        self.rec_tag = Gtk.Button(label="REC")
        self.rec_tag.add_css_class("corner-tag")
        self.rec_tag.add_css_class("corner-tag-rec")
        self.rec_tag.set_halign(Gtk.Align.END)
        self.rec_tag.set_valign(Gtk.Align.END)
        self.rec_tag.connect("clicked", self.on_record_clicked)
        rec_right_click = Gtk.GestureClick.new()
        rec_right_click.set_button(3)
        rec_right_click.connect("released", self.on_rec_mode_cycle)
        self.rec_tag.add_controller(rec_right_click)
        self.cover_overlay.add_overlay(self.rec_tag)

        card.append(self.cover_overlay)

        # --- Row 3: tracklist, permanently visible, scrolls past ~5-6 rows ---
        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(-1, _TRACKLIST_HEIGHT)
        track_scroll.set_hexpand(True)
        track_scroll.add_css_class("tracklist-panel")

        self.track_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.track_list_box.add_css_class("tracklist-container")
        track_scroll.set_child(self.track_list_box)
        card.append(track_scroll)

        # --- Row 4: Stop / Volume (EQ strip behind it) / Mute / Play ---
        control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("control-btn")
        btn_stop.connect("clicked", self.on_stop)
        control_row.append(btn_stop)

        # EQ strip painted behind the volume slider; set_measure_overlay
        # keeps the slider (not the FILL eq_strip) driving the overlay's size.
        self.eq_strip = EqStrip()
        self.eq_strip.set_halign(Gtk.Align.FILL)
        self.eq_strip.set_valign(Gtk.Align.CENTER)

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)
        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)
        self._pre_boost_vol: float | None = None
        self.vol_slider.connect("boost-toggled", self.on_boost_toggled)
        self.vol_slider.set_hexpand(True)

        vol_overlay = Gtk.Overlay()
        vol_overlay.set_child(self.eq_strip)
        vol_overlay.add_overlay(self.vol_slider)
        vol_overlay.set_measure_overlay(self.vol_slider, True)
        vol_overlay.set_hexpand(True)
        control_row.append(vol_overlay)

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
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self._set_genre(None)
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.eq_strip.set_active(False)
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
        self._vol = 0.0
        self._bitrate = None
        self._channels = None
        self._bt = False
        self._device_name = None
        self._update_readout()
        self._rec_mode = "full"
        self._rec_active = False
        self._rec_elapsed = 0
        self._update_rec_tag()
        self.clear_cover()
        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None

        self._sync_tracklist()

    def _update_readout(self):
        parts = []
        parts.append(f"{int(self._vol * 100)}%")
        if self._bitrate:
            parts.append(f"{self._bitrate}k")
        if self._channels:
            parts.append("Stereo" if self._channels == 2 else "Mono" if self._channels == 1 else f"{self._channels}Ch")
        if self._bt:
            parts.append("BT")
        if self._device_name:
            parts.append(self._device_name)
        self.lbl_readout.set_text(" · ".join(parts))

    def _update_rec_tag(self):
        letter = _REC_MODE_LABELS[self._rec_mode]
        self.rec_tag.set_label(f"REC·{letter}")
        if self._rec_active:
            self.rec_tag.add_css_class("active")
            m, s = divmod(self._rec_elapsed, 60)
            self.rec_tag.set_tooltip_text(f"Recording {m:02d}:{s:02d} · left-click to stop · right-click: mode")
        else:
            self.rec_tag.remove_css_class("active")
            self.rec_tag.set_tooltip_text("Left-click to record · right-click: mode")

    def get_current_id(self) -> str | None:
        return self._cur_station_id

    def get_current_track(self) -> tuple[str | None, str | None]:
        return self._cur_artist, self._cur_title

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
            album = html.escape(meta.get('album') or 'Unknown Album')
            year = meta.get('year')
            header = f"<b>{album}</b>" + (f"  ·  {html.escape(str(year))}" if year else "")
            album_lbl.set_markup(header)
            album_lbl.set_wrap(True)
            album_lbl.set_max_width_chars(30)
            self.track_list_box.append(album_lbl)

            # Individual track matrix layout injection
            canonical_track = meta.get("track", "")
            for track_item in meta["tracklist"]:
                num = track_item.get("number", 0)
                name = track_item.get("name", "")
                dur = _fmt_duration(track_item.get("duration_ms"))

                track_lbl = Gtk.Label(xalign=0.0)
                escaped_name = html.escape(name)
                line = f"{num}. {escaped_name}" + (f"  <i>{dur}</i>" if dur else "")

                if name == canonical_track:
                    track_lbl.set_markup(f"<b>{line}</b>")
                else:
                    track_lbl.set_markup(line)

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

    def _async_resync_tracklist(self, artist: str, title: str):
        import time
        time.sleep(3.0)  # give sqlch-enrich time to write enriched.json
        if self._cur_artist != artist or self._cur_title != title:
            return  # track already changed, bail
        GLib.idle_add(self._sync_tracklist)

    def _apply_cover_path(self, path: str, artist: str, title: str) -> bool:
        if self._cur_artist == artist and self._cur_title == title:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, _COVER_SIZE, _COVER_SIZE, True)
                self.cover_img.set_from_pixbuf(pb)
                self.cover_stack.set_visible_child_name("art")
            except Exception:
                self.clear_cover()
        return False

    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool,
                          channels: int | None, recording: dict | None = None, fmt: str | None = None,
                          device_name: str | None = None):
        self._loaded = playing
        self.btn_toggle.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")
        self.eq_strip.set_active(playing)

        # Block signals temporarily to prevent loopback configuration cascades
        self.vol_slider.handler_block(self._vol_handler)
        self.vol_adj.set_value(vol)
        self.vol_slider.handler_unblock(self._vol_handler)

        if muted:
            self.btn_mute.set_icon_name("audio-volume-muted-symbolic")
        elif vol < 0.4:
            self.btn_mute.set_icon_name("audio-volume-low-symbolic")
        elif vol < 0.8:
            self.btn_mute.set_icon_name("audio-volume-medium-symbolic")
        else:
            self.btn_mute.set_icon_name("audio-volume-high-symbolic")

        self._vol = vol
        self._bitrate = bitrate
        self._channels = channels
        self._bt = bt
        self._device_name = device_name
        self._update_readout()

        if fmt:
            self.lbl_format_tag.set_text(fmt)
            self.lbl_format_tag.set_visible(True)
        else:
            self.lbl_format_tag.set_visible(False)

        rec = recording or {}
        self._rec_active = bool(rec.get("active"))
        mode = rec.get("mode")
        if mode in ("full", "track"):
            self._rec_mode = mode
        self._rec_elapsed = int(rec.get("elapsed", 0))
        self._update_rec_tag()

    def on_record_clicked(self, btn):
        daemon.send({"cmd": "record", "action": "toggle", "mode": self._rec_mode})

    def on_rec_mode_cycle(self, gesture, n_press, x, y):
        if self._rec_active:
            return  # mode locked while a take is rolling
        modes = ("full", "track")
        i = modes.index(self._rec_mode)
        self._rec_mode = modes[(i + 1) % len(modes)]
        self._update_rec_tag()

    def on_toggle_play(self, btn):
        if self._loaded:
            daemon.send({"cmd": "pause"})
        else:
            daemon.send({"cmd": "play", "query": "__last__"})

    def on_stop(self, btn):
        daemon.send({"cmd": "stop"})

    def on_toggle_mute(self, btn):
        import subprocess
        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                       stdout=subprocess.DEVNULL)

    def on_vol_changed(self, slider, val):
        self._vol = val
        self._update_readout()
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)

    def on_boost_toggled(self, slider, active):
        import subprocess
        if active:
            self._pre_boost_vol = self.vol_adj.get_value()
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.20"], stdout=subprocess.DEVNULL)
        else:
            restore = self._pre_boost_vol if self._pre_boost_vol is not None else 0.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{restore:.2f}"], stdout=subprocess.DEVNULL)
            self._pre_boost_vol = None
