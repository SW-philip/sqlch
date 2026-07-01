"""Interactive Station Library interface with grouped lists and inline CRUD editing."""

from gi.repository import Gtk, Gdk
from .. import library, daemon, palette

def format_live_text(artist: str | None, title: str | None) -> str:
    parts = [p for p in (artist, title) if p]
    if not parts:
        return ""
    return "♫ " + " — ".join(parts)

class StationListPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.win = parent_window

        # Add manual configuration trigger bar
        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_box.add_css_class("list-header")
        self.ent_name = Gtk.Entry(placeholder_text="Station Name")
        self.ent_name.set_hexpand(True)
        self.ent_url = Gtk.Entry(placeholder_text="Stream URL")
        self.ent_url.set_hexpand(True)
        btn_add = Gtk.Button(icon_name="list-add-symbolic")
        btn_add.connect("clicked", self.on_add_station)
        
        add_box.append(self.ent_name)
        add_box.append(self.ent_url)
        add_box.append(btn_add)
        self.append(add_box)

        # Scrolled containment tree
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.list_box)
        self.append(scroll)

        self._rows_map = {}
        self.refresh()

    def refresh(self):
        """Rebuild entire listing catalog mapping."""
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        self._rows_map.clear()

        stations = library.get_station_list()
        
        # Sort catalog entries cleanly by grouping parameters
        groups = {}
        for s in stations:
            g = s.get("group", "Unsorted")
            groups.setdefault(g, []).append(s)

        colors = palette.load()
        for g_name in sorted(groups.keys()):
            # Inject structural separator heading label
            lbl = Gtk.Label(xalign=0.0)
            lbl.set_markup(f"<span foreground='{colors['BAR']}' weight='bold'>{g_name}</span>")
            lbl.set_margin_top(8)
            lbl.set_margin_bottom(4)
            self.list_box.append(lbl)

            def _freq(v):
                try:
                    return float(str(v or "0").split()[0])
                except (ValueError, IndexError):
                    return 0.0

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

    def on_row_clicked(self, gesture, n_press, x, y, station):
        button = gesture.get_current_button()
        if button == Gdk.BUTTON_PRIMARY:
            daemon.send({"cmd": "play", "query": station["id"]})
        elif button == Gdk.BUTTON_SECONDARY:
            self.show_context_menu(gesture.get_widget(), station)

    def show_context_menu(self, widget, station):
        popover = Gtk.Popover()
        popover.set_parent(widget)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        # Modification entries
        ent_edit_name = Gtk.Entry(text=station["name"])
        ent_edit_url = Gtk.Entry(text=station["url"])
        def _freq(v):
            try:
                return float(str(v or "0").split()[0])
            except (ValueError, IndexError):
                return 0.0
        ent_edit_freq = Gtk.Entry(text=f"{_freq(station.get('frequency')):.1f}")
        ent_edit_group = Gtk.Entry(text=station.get("group", "Unsorted"))
        
        btn_save = Gtk.Button(label="Save Modifications")
        btn_save.connect("clicked", lambda b: self.on_save_edit(popover, station["id"], ent_edit_name.get_text(), ent_edit_url.get_text(), ent_edit_freq.get_text(), ent_edit_group.get_text()))
        
        btn_del = Gtk.Button(label="Delete Station")
        btn_del.add_css_class("destructive-action")
        btn_del.connect("clicked", lambda b: self.on_delete_station(popover, station["id"]))

        vbox.append(Gtk.Label(label="Edit Name:", xalign=0.0))
        vbox.append(ent_edit_name)
        vbox.append(Gtk.Label(label="Edit Stream URL:", xalign=0.0))
        vbox.append(ent_edit_url)
        vbox.append(Gtk.Label(label="Frequency:", xalign=0.0))
        vbox.append(ent_edit_freq)
        vbox.append(Gtk.Label(label="Category Group:", xalign=0.0))
        vbox.append(ent_edit_group)
        vbox.append(btn_save)
        vbox.append(Gtk.Separator())
        vbox.append(btn_del)
        
        popover.set_child(vbox)
        popover.popup()

    def on_save_edit(self, popover, station_id, name, url, freq_str, group):
        library.update(station_id, name, url)
        try:
            library.set_frequency(station_id, float(freq_str))
        except ValueError:
            pass
        library.set_group(station_id, group)
        popover.popdown()
        self.refresh()

    def on_delete_station(self, popover, station_id):
        library.remove(station_id)
        popover.popdown()
        self.refresh()

    def on_add_station(self, btn):
        name = self.ent_name.get_text().strip()
        url = self.ent_url.get_text().strip()
        if name and url:
            err = library.add_url(name, url)
            if not err:
                self.ent_name.set_text("")
                self.ent_url.set_text("")
                self.refresh()

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