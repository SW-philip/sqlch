"""Now Playing layout, stream management controls, and metadata rendering."""

import html
import threading
from pathlib import Path
from gi.repository import Gtk, GLib, GdkPixbuf

from .. import daemon, metadata

class NowPlayingPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_margin_start(14)
        self.set_margin_end(14)
        self.set_margin_top(14)
        self.set_margin_bottom(14)
        self.win = parent_window

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.add_css_class("card")
        
        # Cover Art
        self.cover_img = Gtk.Image()
        self.cover_img.set_pixel_size(96)
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

        # Playback controllers row
        ctrl_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ctrl_row.set_halign(Gtk.Align.CENTER)
        
        self.btn_toggle = Gtk.Button()
        self.btn_toggle.add_css_class("control-btn")
        self.btn_toggle.connect("clicked", self.on_toggle_play)
        
        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("control-btn")
        btn_stop.connect("clicked", self.on_stop)
        
        ctrl_row.append(self.btn_toggle)
        ctrl_row.append(btn_stop)
        self.append(ctrl_row)

        # Volume block
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        vol_box.add_css_class("vol-slider")
        self.btn_mute = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self.btn_mute.set_has_frame(False)
        self.btn_mute.connect("clicked", self.on_toggle_mute)
        
        self.vol_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=1.3, step_increment=0.05)
        self.vol_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.vol_adj)
        self.vol_scale.set_hexpand(True)
        self.vol_scale.set_draw_value(False)
        self.vol_scale.connect("value-changed", self.on_vol_changed)
        
        vol_box.append(self.btn_mute)
        vol_box.append(self.vol_scale)
        self.append(vol_box)

        # Signal / Technical specifications footprint row
        self.tech_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.tech_box.set_halign(Gtk.Align.CENTER)
        self.lbl_bitrate = Gtk.Label()
        self.lbl_bitrate.add_css_class("tech-badge")
        self.lbl_channels = Gtk.Label()
        self.lbl_channels.add_css_class("tech-badge")
        self.lbl_bt = Gtk.Label(label="BT")
        self.lbl_bt.add_css_class("tech-badge")
        
        self.tech_box.append(self.lbl_bitrate)
        self.tech_box.append(self.lbl_channels)
        self.tech_box.append(self.lbl_bt)
        self.append(self.tech_box)

        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None
        self.reset_ui()

    def clear_cover(self):
        self.cover_img.set_from_icon_name("audio-x-generic-symbolic")

    def reset_ui(self):
        self.lbl_title.set_markup("<b>Not Playing</b>")
        self.lbl_artist.set_text("Select a station from the library")
        self.lbl_genre.set_text("")
        self.btn_toggle.set_icon_name("media-playback-start-symbolic")
        self.tech_box.set_visible(False)
        self.clear_cover()
        self._cur_station_id = None
        self._cur_artist = None
        self._cur_title = None

    def get_current_id(self) -> str | None:
        return self._cur_station_id

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
            self._cur_artist, self._cur_title = None, None
        else:
            self.lbl_title.set_text(title or "Unknown Track")
            self.lbl_artist.set_text(artist or "Unknown Artist")
            
            if artist != self._cur_artist or title != self._cur_title:
                self._cur_artist = artist
                self._cur_title = title
                metadata.run_enrich(artist, title)
                threading.Thread(target=self._async_fetch_cover, args=(artist, title), daemon=True).start()

        genre = metadata.get_icy_genre()
        self.lbl_genre.set_text(genre if genre else "")
        self.lbl_genre.set_visible(bool(genre))

    def _async_fetch_cover(self, artist: str, title: str):
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
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 96, 96, True)
                self.cover_img.set_from_pixbuf(pb)
            except Exception:
                self.clear_cover()
        return False

    def update_indicators(self, bitrate: int | None, vol: float, muted: bool, bt: bool, playing: bool, channels: int | None):
        self.btn_toggle.set_icon_name("media-playback-pause-symbolic" if playing else "media-playback-start-symbolic")
        
        # Lock volume signal circular execution updates
        self.vol_scale.block_signals()
        self.vol_adj.set_value(vol)
        self.vol_scale.unblock_signals()

        if muted:
            self.btn_mute.set_icon_name("audio-volume-muted-symbolic")
        elif vol < 0.4:
            self.btn_mute.set_icon_name("audio-volume-low-symbolic")
        elif vol < 0.8:
            self.btn_mute.set_icon_name("audio-volume-medium-symbolic")
        else:
            self.btn_mute.set_icon_name("audio-volume-high-symbolic")

        has_tech = False
        if bitrate:
            self.lbl_bitrate.set_text(f"{bitrate}k")
            self.lbl_bitrate.set_visible(True)
            has_tech = True
        else:
            self.lbl_bitrate.set_visible(False)

        if channels:
            self.lbl_channels.set_text("Stereo" if channels == 2 else "Mono" if channels == 1 else f"{channels}Ch")
            self.lbl_channels.set_visible(True)
            has_tech = True
        else:
            self.lbl_channels.set_visible(False)

        self.lbl_bt.set_visible(bt)
        if bt:
            has_tech = True

        self.tech_box.set_visible(has_tech)

    def on_toggle_play(self, btn):
        daemon.send({"command": "toggle"})

    def on_stop(self, btn):
        daemon.send({"command": "stop"})

    def on_toggle_mute(self, btn):
        daemon.send({"command": "mute"})

    def on_vol_changed(self, scale):
        val = scale.get_value()
        # Direct pass parameters to daemon volume configuration layer
        import subprocess
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"], stdout=subprocess.DEVNULL)