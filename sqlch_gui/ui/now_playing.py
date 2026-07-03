"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf

from .. import daemon, metadata
from .knob import RotaryKnob

class NowPlayingPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_valign(Gtk.Align.CENTER)
        self.win = parent_window

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")

        # --- Dual-Sided Album Deck Layout Container ---
        deck_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        deck_box.set_halign(Gtk.Align.CENTER)

        # Hero cover art elements (Front side)[cite: 10]
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(120)[cite: 10]
        self.cover_placeholder = Gtk.Label(label="♪")[cite: 10]
        self.cover_placeholder.add_css_class("cover-glyph")[cite: 10]

        self.cover_stack = Gtk.Stack()[cite: 10]
        self.cover_stack.add_css_class("cover-art")[cite: 10]
        self.cover_stack.add_named(self.cover_placeholder, "placeholder")[cite: 10]
        self.cover_stack.add_named(self.cover_img, "art")[cite: 10]
        self.clear_cover()[cite: 10]

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
        self.stack_wrapper.set_child(self.deck_stack)
        deck_box.append(self.stack_wrapper)

        # Index Tag Toggle Button on the right
        self.flip_btn = Gtk.Button(icon_name="object-flip-horizontal-symbolic")
        self.flip_btn.add_css_class("flip-tag-btn")
        self.flip_btn.set_valign(Gtk.Align.CENTER)
        self.flip_btn.connect("clicked", self.on_flip_clicked)
        deck_box.append(self.flip_btn)

        card.append(deck_box)

        # Meta details text stack, centered below the art[cite: 10]
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)[cite: 10]
        text_box.set_halign(Gtk.Align.CENTER)[cite: 10]
        self.lbl_title = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)[cite: 10]
        self.lbl_title.add_css_class("meta-title")[cite: 10]
        self.lbl_title.set_wrap(True)[cite: 10]
        self.lbl_title.set_max_width_chars(36)[cite: 10]

        self.lbl_artist = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)[cite: 10]
        self.lbl_artist.add_css_class("meta-artist")[cite: 10]
        self.lbl_artist.set_wrap(True)[cite: 10]
        self.lbl_artist.set_max_width_chars(36)[cite: 10]

        self.lbl_genre = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER)[cite: 10]
        self.lbl_genre.add_css_class("meta-genre")[cite: 10]

        text_box.append(self.lbl_title)[cite: 10]
        text_box.append(self.lbl_artist)[cite: 10]
        text_box.append(self.lbl_genre)[cite: 10]
        card.append(text_box)[cite: 10]
        self.append(card)[cite: 10]

        # Control deck card, organized as a hub[cite: 10]
        deck = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)[cite: 10]
        deck.add_css_class("card")[cite: 10]

        # Hub row[cite: 10]
        hub_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)[cite: 10]
        hub_row.set_halign(Gtk.Align.CENTER)[cite: 10]

        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")[cite: 10]
        btn_stop.add_css_class("control-btn")[cite: 10]
        btn_stop.connect("clicked", self.on_stop)[cite: 10]
        btn_stop.set_valign(Gtk.Align.CENTER)[cite: 10]

        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.3, step_increment=0.05)[cite: 10]

        self.vol_knob = RotaryKnob(self.vol_adj)[cite: 10]
        self.vol_knob.set_valign(Gtk.Align.CENTER)[cite: 10]
        self._vol_handler = self.vol_knob.connect("value-changed", self.on_vol_changed)[cite: 10]

        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")[cite: 10]
        self.btn_mute.add_css_class("control-btn")[cite: 10]
        self.btn_mute.set_valign(Gtk.Align.CENTER)[cite: 10]
        self.btn_mute.connect("clicked", self.on_toggle_mute)[cite: 10]

        hub_row.append(btn_stop)[cite: 10]
        hub_row.append(self.vol_knob)[cite: 10]
        hub_row.append(self.btn_mute)[cite: 10]
        deck.append(hub_row)[cite: 10]

        # Primary transport at 6 o'clock[cite: 10]
        self.btn_toggle = Gtk.Button()[cite: 10]
        self.btn_toggle.add_css_class("control-btn")[cite: 10]
        self.btn_toggle.add_css_class("primary")[cite: 10]
        self.btn_toggle.set_halign(Gtk.Align.CENTER)[cite: 10]
        self.btn_toggle.connect("clicked", self.on_toggle_play)[cite: 10]
        deck.append(self.btn_toggle)[cite: 10]

        # Readout strip[cite: 10]
        self.tech_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)[cite: 10]
        self.tech_box.set_halign(Gtk.Align.CENTER)[cite: 10]

        self.lbl_vol_percent = Gtk.Label(label="0%")[cite: 10]
        self.lbl_vol_percent.add_css_class("tech-badge")[cite: 10]
        self.lbl_vol_percent.set_width_chars(5)[cite: 10]

        self.lbl_bitrate = Gtk.Label()[cite: 10]
        self.lbl_bitrate.add_css_class("tech-badge")[cite: 10]
        self.lbl_channels = Gtk.Label()[cite: 10]
        self.lbl_channels.add_css_class("tech-badge")[cite: 10]
        self.lbl_bt = Gtk.Label(label="BT")[cite: 10]
        self.lbl_bt.add_css_class("tech-badge")[cite: 10]

        self.tech_box.append(self.lbl_vol_percent)[cite: 10]
        self.tech_box.append(self.lbl_bitrate)[cite: 10]
        self.tech_box.append(self.lbl_channels)[cite: 10]
        self.tech_box.append(self.lbl_bt)[cite: 10]
        deck.append(self.tech_box)[cite: 10]
        self.append(deck)[cite: 10]

        self._cur_station_id = None[cite: 10]
        self._cur_artist = None[cite: 10]
        self._cur_title = None[cite: 10]
        self._loaded = False[cite: 10]
        self.reset_ui()[cite: 10]

    def clear_cover(self):
        self.cover_stack.set_visible_child_name("placeholder")[cite: 10]

    def reset_ui(self):
        self.lbl_title.set_markup("<b>Not Playing</b>")[cite: 10]
        self.lbl_artist.set_text("Select a station from the library")[cite: 10]
        self.lbl_genre.set_text("")[cite: 10]
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")[cite: 10]
        self.lbl_bitrate.set_visible(False)[cite: 10]
        self.lbl_channels.set_visible(False)[cite: 10]
        self.lbl_bt.set_visible(False)[cite: 10]
        self.clear_cover()[cite: 10]
        self._cur_station_id = None[cite: 10]
        self._cur_artist = None[cite: 10]
        self._cur_title = None[cite: 10]

        # Sync back-plate layout status
        self.stack_wrapper.remove_css_class("flipped")
        self.deck_stack.set_visible_child_name("front")

    def get_current_id(self) -> str | None:
        return self._cur_station_id[cite: 10]

    def get_current_track(self) -> tuple[str | None, str | None]:
        return self._cur_artist, self._cur_title[cite: 10]

    def _sync_back_plate(self, title: str, artist: str):
        """Safely cleans and updates the ledger back-plate markup strings."""
        while child := self.track_list_box.get_first_child():
            self.track_list_box.remove(child)

        lbl_info = Gtk.Label(xalign=0.0)
        lbl_info.set_markup(f"<b>A面:</b>\n{html.escape(title or 'No Track')}\n\n<i>{html.escape(artist or 'Unknown Artist')}</i>")
        lbl_info.set_wrap(True)
        lbl_info.set_max_width_chars(14)
        self.track_list_box.append(lbl_info)

    def on_flip_clicked(self, btn):
        current = self.deck_stack.get_visible_child_name()
        if current == "front":
            self.stack_wrapper.add_css_class("flipped")
            self.deck_stack.set_visible_child_name("back")
            self._sync_back_plate(self._cur_title, self._cur_artist)
        else:
            self.stack_wrapper.remove_css_class("flipped")
            self.deck_stack.set_visible_child_name("front")

    def update(self, resp: dict | None, icy: tuple[str | None, str | None]):
        if not resp or not resp.get("ok") or not resp.get("current"):[cite: 10]
            self.reset_ui()[cite: 10]
            return[cite: 10]

        curr = resp["current"][cite: 10]
        self._cur_station_id = curr.get("id")[cite: 10]
        station_name = curr.get("name", "Unknown Station")[cite: 10]

        raw_artist, raw_title = icy[cite: 10]
        artist = raw_artist.strip() if raw_artist else ""[cite: 10]
        title = raw_title.strip() if raw_title else ""[cite: 10]

        if not artist and not title:[cite: 10]
            self.lbl_title.set_markup(f"<b>{html.escape(station_name)}</b>")[cite: 10]
            self.lbl_artist.set_text("Live Stream")[cite: 10]
            self.clear_cover()[cite: 10]
            self._cur_artist, self._cur_title = None, None[cite: 10]
        else:
            self.lbl_title.set_text(title or "Unknown Track")[cite: 10]
            self.lbl_artist.set_text(artist or "Unknown Artist")[cite: 10]

            if artist != self._cur_artist or title != self._cur_title:[cite: 10]
                self._cur_artist = artist[cite: 10]
                self._cur_title = title[cite: 10]
                metadata.run_enrich(artist, title)[cite: 10]
                threading.Thread(target=self._async_fetch_cover, args=(artist, title), daemon=True).start()[cite: 10]

        # Push real-time updates directly to the back ledger if open
        if self.deck_stack.get_visible_child_name() == "back":
            self._sync_back_plate(self._cur_title, self._cur_artist)

        genre = metadata.get_icy_genre()[cite: 10]
        self.lbl_genre.set_text(genre if genre else "")[cite: 10]
        self.lbl_genre.set_visible(bool(genre))[cite: 10]

    def _async_fetch_cover(self, artist: str, title: str):
        import time[cite: 10]
        time.sleep(3.0)  # give sqlch-enrich time to write enriched.json[cite: 10]
        if self._cur_artist != artist or self._cur_title != title:[cite: 10]
            return  # track already changed, bail[cite: 10]
        path, mode = metadata.get_cover_info(artist, title)[cite: 10]
        if mode == "remote" and path:[cite: 10]
            import hashlib[cite: 10]
            h = hashlib.md5(f"{artist.lower()}|{title.lower()}".encode()).hexdigest()[cite: 10]
            local_path = metadata.COVERS_DIR / f"{h}.jpg"[cite: 10]
            if metadata.download_cover(path, local_path):[cite: 10]
                path = str(local_path)[cite: 10]
                mode = "local"[cite: 10]

        if mode == "local" and path and Path(path).exists():[cite: 10]
            GLib.idle_add(self._apply_cover_path, path, artist, title)[cite: 10]

    def _apply_cover_path(self, path: str, artist: str, title: str) -> bool:
        if self._cur_artist == artist and self._cur_title == title:[cite: 10]
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 120, 120, True)[cite: 10]
                self.cover_img.set_from_pixbuf(pb)[cite: 10]
                self.cover_stack.set_visible_child_name("art")[cite: 10]
            except Exception:[cite: 10]
                self.clear_cover()[cite: 10]
        return False[cite: 10]

    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool, channels: int | None):
        self._loaded = playing[cite: 10]
        self.btn_toggle.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")[cite: 10]

        # Block signals temporarily to prevent loopback configuration cascades[cite: 10]
        self.vol_knob.handler_block(self._vol_handler)[cite: 10]
        self.vol_adj.set_value(vol)[cite: 10]
        self.vol_knob.handler_unblock(self._vol_handler)[cite: 10]

        # Update the text readout percentage[cite: 10]
        self.lbl_vol_percent.set_text(f"{int(vol * 100)}%")[cite: 10]

        if muted:[cite: 10]
            self.btn_mute.set_icon_name("audio-volume-muted-symbolic")[cite: 10]
        elif vol < 0.4:[cite: 10]
            self.btn_mute.set_icon_name("audio-volume-low-symbolic")[cite: 10]
        elif vol < 0.8:[cite: 10]
            self.btn_mute.set_icon_name("audio-volume-medium-symbolic")[cite: 10]
        else:[cite: 10]
            self.btn_mute.set_icon_name("audio-volume-high-symbolic")[cite: 10]

        if bitrate:[cite: 10]
            self.lbl_bitrate.set_text(f"{bitrate}k")[cite: 10]
            self.lbl_bitrate.set_visible(True)[cite: 10]
        else:[cite: 10]
            self.lbl_bitrate.set_visible(False)[cite: 10]

        if channels:[cite: 10]
            self.lbl_channels.set_text("Stereo" if channels == 2 else "Mono" if channels == 1 else f"{channels}Ch")[cite: 10]
            self.lbl_channels.set_visible(True)[cite: 10]
        else:[cite: 10]
            self.lbl_channels.set_visible(False)[cite: 10]

        self.lbl_bt.set_visible(bt)[cite: 10]

    def on_toggle_play(self, btn):
        if self._loaded:[cite: 10]
            daemon.send({"cmd": "pause"})[cite: 10]
        else:
            daemon.send({"cmd": "play", "query": "__last__"})[cite: 10]

    def on_stop(self, btn):
        daemon.send({"cmd": "stop"})[cite: 10]

    def on_toggle_mute(self, btn):
        import subprocess[cite: 10]
        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],[cite: 10]
                       stdout=subprocess.DEVNULL)

    def on_vol_changed(self, knob, val):
        # Dynamically push numeric modifications into stdout subsystem[cite: 10]
        self.lbl_vol_percent.set_text(f"{int(val * 100)}%")[cite: 10]
        import subprocess[cite: 10]
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)[cite: 10]
