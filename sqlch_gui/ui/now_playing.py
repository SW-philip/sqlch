"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf

from .. import daemon, metadata
from .controls import ThreadSlider, RecordBubble
from .eq_strip import EqStrip

_REC_MODE_LABELS = {"full": "FULL", "track": "TRK"}

class NowPlayingPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")

        # --- Dual-Sided Album Deck Layout Container ---
        deck_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        deck_box.set_halign(Gtk.Align.CENTER)

        # Hero cover art elements (Front side)
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(120)
        self.cover_placeholder = Gtk.Label(label="♪")
        self.cover_placeholder.add_css_class("cover-glyph")

        self.cover_stack = Gtk.Stack()
        self.cover_stack.add_css_class("cover-art")
        self.cover_stack.add_named(self.cover_placeholder, "placeholder")
        self.cover_stack.add_named(self.cover_img, "art")
        self.clear_cover()

        # Tracklist Matrix Sheet (Back side)
        track_scroll = Gtk.ScrolledWindow()
        track_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        track_scroll.set_size_request(124, 124)
        track_scroll.add_css_class("art-card-back")

        self.track_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.track_list_box.add_css_class("tracklist-container")
        track_scroll.set_child(self.track_list_box)

        # Core physical deck stack switcher
        self.deck_stack = Gtk.Stack()
        self.deck_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.deck_stack.set_transition_duration(250)
        self.deck_stack.add_named(self.cover_stack, "front")
        self.deck_stack.add_named(track_scroll, "back")

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

        # Index Tag Toggle Button on the right
        self.flip_btn = Gtk.Button(icon_name="object-flip-horizontal-symbolic")
        self.flip_btn.add_css_class("flip-tag-btn")
        self.flip_btn.set_valign(Gtk.Align.CENTER)
        self.flip_btn.connect("clicked", self.on_flip_clicked)
        deck_box.append(self.flip_btn)

        card.append(deck_box)

        self.eq_strip = EqStrip()
        self.eq_strip.set_halign(Gtk.Align.CENTER)
        card.append(self.eq_strip)

        # Meta details text stack, centered below the art
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        text_box.set_halign(Gtk.Align.CENTER)
        self.lbl_title = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_title.add_css_class("meta-title")
        self.lbl_title.set_wrap(True)
        self.lbl_title.set_max_width_chars(36)

        self.lbl_artist = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_artist.add_css_class("meta-artist")
        self.lbl_artist.set_wrap(True)
        self.lbl_artist.set_max_width_chars(36)

        self.lbl_genre = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)
        self.lbl_genre.add_css_class("thread-label")

        text_box.append(self.lbl_title)
        text_box.append(self.lbl_artist)
        text_box.append(self.lbl_genre)
        card.append(text_box)
        self.append(card)

        # Control deck card, organized as a hub
        deck = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        deck.add_css_class("card")

        # Hub row
        hub_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hub_row.set_halign(Gtk.Align.CENTER)

        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("control-btn")
        btn_stop.connect("clicked", self.on_stop)
        btn_stop.set_valign(Gtk.Align.CENTER)

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.0, step_increment=0.05)

        self.vol_slider = ThreadSlider(self.vol_adj)
        self._vol_handler = self.vol_slider.connect("value-changed", self.on_vol_changed)

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.add_css_class("control-btn")
        self.btn_mute.set_valign(Gtk.Align.CENTER)
        self.btn_mute.connect("clicked", self.on_toggle_mute)

        self.rec_knob = RecordBubble()
        self.rec_knob.connect("record-toggled", self.on_record_toggled)
        self.rec_knob.connect("mode-changed", self.on_rec_mode_changed)

        self.lbl_rec_mode = Gtk.Label(label=_REC_MODE_LABELS[self.rec_knob.mode])
        self.lbl_rec_mode.add_css_class("small-badge")
        self.lbl_rec_mode.set_halign(Gtk.Align.END)
        self.lbl_rec_mode.set_valign(Gtk.Align.END)
        self.lbl_rec_mode.set_can_target(False)

        rec_bubble_overlay = Gtk.Overlay()
        rec_bubble_overlay.set_child(self.rec_knob)
        rec_bubble_overlay.add_overlay(self.lbl_rec_mode)

        rec_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        rec_wrap.set_valign(Gtk.Align.CENTER)
        rec_wrap.set_halign(Gtk.Align.CENTER)
        rec_wrap.append(rec_bubble_overlay)
        lbl_rec_tag = Gtk.Label(label="REC")
        lbl_rec_tag.add_css_class("knob-tag")
        rec_wrap.append(lbl_rec_tag)

        hub_row.append(rec_wrap)
        hub_row.append(btn_stop)
        hub_row.append(self.btn_mute)
        deck.append(hub_row)

        # Full-width zipper volume row, sewn in below the hub
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_row.append(self.vol_slider)
        deck.append(vol_row)

        lbl_vol_tag = Gtk.Label(label="VOL")
        lbl_vol_tag.add_css_class("knob-tag")
        lbl_vol_tag.set_halign(Gtk.Align.START)
        deck.append(lbl_vol_tag)

        # Primary transport at 6 o'clock
        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.add_css_class("primary")
        self.btn_toggle.set_halign(Gtk.Align.CENTER)
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        deck.append(self.btn_toggle)

        # Readout strip
        self.tech_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.tech_box.set_halign(Gtk.Align.CENTER)

        self.lbl_vol_percent = Gtk.Label(label="0%")
        self.lbl_vol_percent.add_css_class("tech-badge")
        self.lbl_vol_percent.set_width_chars(5)

        self.lbl_rec = Gtk.Label()
        self.lbl_rec.add_css_class("tech-badge")
        self.lbl_rec.add_css_class("rec-badge")

        self.lbl_bitrate = Gtk.Label()
        self.lbl_bitrate.add_css_class("tech-badge")
        self.lbl_channels = Gtk.Label()
        self.lbl_channels.add_css_class("tech-badge")
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

        deck_overlay = Gtk.Overlay()
        deck_overlay.set_child(deck)
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
        deck_overlay.add_overlay(lbl_brand)
        self.append(deck_overlay)

        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None
        self._loaded = False
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
        self.lbl_bitrate.set_visible(False)
        self.lbl_channels.set_visible(False)
        self.lbl_bt.set_visible(False)
        self.lbl_live_tag.set_visible(False)
        self.lbl_format_tag.set_visible(False)
        self.lbl_device.set_visible(False)
        self.rec_knob.set_state(False, None)
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[self.rec_knob.mode])
        self.lbl_rec.set_visible(False)
        self.clear_cover()
        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None

        # Sync back-plate layout status
        self.stack_wrapper.remove_css_class("flipped")
        self.deck_stack.set_visible_child_name("front")

    def get_current_id(self) -> str | None:
        return self._cur_station_id

    def get_current_track(self) -> tuple[str | None, str | None]:
        return self._cur_artist, self._cur_title

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

    def on_flip_clicked(self, btn):
        current = self.deck_stack.get_visible_child_name()
        if current == "front":
            self.stack_wrapper.add_css_class("flipped")
            self.deck_stack.set_visible_child_name("back")
            self._sync_back_plate()
        else:
            self.stack_wrapper.remove_css_class("flipped")
            self.deck_stack.set_visible_child_name("front")

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
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 120, 120, True)
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

        # Update the text readout percentage
        self.lbl_vol_percent.set_text(f"{int(vol * 100)}%")

        if muted:
            self.btn_mute.set_icon_name("audio-volume-muted-symbolic")
        elif vol < 0.4:
            self.btn_mute.set_icon_name("audio-volume-low-symbolic")
        elif vol < 0.8:
            self.btn_mute.set_icon_name("audio-volume-medium-symbolic")
        else:
            self.btn_mute.set_icon_name("audio-volume-high-symbolic")

        if bitrate:
            self.lbl_bitrate.set_text(f"{bitrate}k")
            self.lbl_bitrate.set_visible(True)
        else:
            self.lbl_bitrate.set_visible(False)

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

        if device_name:
            self.lbl_device.set_text(device_name)
            self.lbl_device.set_visible(True)
        else:
            self.lbl_device.set_visible(False)

        rec = recording or {}
        active = bool(rec.get("active"))
        self.rec_knob.set_state(active, rec.get("mode"))
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[self.rec_knob.mode])
        if active:
            m, s = divmod(int(rec.get("elapsed", 0)), 60)
            self.lbl_rec.set_text(f"REC {m:02d}:{s:02d}")
        self.lbl_rec.set_visible(active)

    def on_record_toggled(self, knob, mode):
        daemon.send({"cmd": "record", "action": "toggle", "mode": mode})

    def on_rec_mode_changed(self, knob, mode):
        self.lbl_rec_mode.set_text(_REC_MODE_LABELS[mode])

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
        # Dynamically push numeric modifications into stdout subsystem
        self.lbl_vol_percent.set_text(f"{int(val * 100)}%")
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)
