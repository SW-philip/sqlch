"""Network Radio-Browser directory scanning interface."""

import threading
from gi.repository import Gtk, GLib
from .. import radiobrowser

GENRE_TAGS = ["Jazz", "News", "Rock", "Electronic", "Classical", "Talk", "Ambient", "Sports", "80s"]


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
        self.ent_query = Gtk.Entry(placeholder_text="Search worldwide directory...")
        self.ent_query.set_hexpand(True)
        self.ent_query.connect("activate", self.on_search)

        btn_go = Gtk.Button(icon_name="edit-find-symbolic")
        btn_go.connect("clicked", self.on_search)

        search_box.append(self.ent_query)
        search_box.append(btn_go)
        self.append(search_box)

        # Scoped Container for Category Discovery
        self.discovery_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.browse_title = Gtk.Label(xalign=0.0)
        self.browse_title.set_markup("<span size='small' weight='bold' alpha='70%'>BROWSE CATEGORIES</span>")
        self.discovery_container.append(self.browse_title)

        # Genre browse grid
        self.tag_grid = Gtk.FlowBox()
        self.tag_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.tag_grid.set_max_children_per_line(4)
        self.tag_grid.set_row_spacing(6)
        self.tag_grid.set_column_spacing(6)
        for tag in GENRE_TAGS:
            btn = Gtk.Button(label=tag.lower())
            btn.add_css_class("tag-chip")
            btn.connect("clicked", lambda b, t=tag: self.on_tag_clicked(t))
            self.tag_grid.append(btn)
        self.discovery_container.append(self.tag_grid)
        self.append(self.discovery_container)

        # Reset active selection banner
        self.reset_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.reset_banner.set_visible(False)
        self.lbl_active_filter = Gtk.Label(xalign=0.0)
        self.lbl_active_filter.add_css_class("meta-genre")

        btn_clear = Gtk.Button(icon_name="edit-clear-symbolic")
        btn_clear.add_css_class("tag-chip")
        btn_clear.set_tooltip_text("Clear filter and show directories")
        btn_clear.connect("clicked", self.reset_discovery_view)

        self.reset_banner.append(self.lbl_active_filter)
        self.reset_banner.append(btn_clear)
        self.append(self.reset_banner)

        # Output catalog matrix viewport
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.results_box = Gtk.ListBox()
        self.results_box.add_css_class("list-plate")
        self.results_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.results_box)
        self.append(scroll)

        self.spinner = Gtk.Spinner()
        self.append(self.spinner)

    def on_tag_clicked(self, tag: str):
        self.discovery_container.set_visible(False)
        self.lbl_active_filter.set_markup(f"Active Genre: <b>{tag}</b>")
        self.reset_banner.set_visible(True)
        self.spinner.start()
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        threading.Thread(target=self._async_search_by_tag, args=(tag,), daemon=True).start()

    def _async_search_by_tag(self, tag: str):
        results = radiobrowser.run_search_by_tag(tag)
        GLib.idle_add(self._apply_results, results)

    def on_search(self, button=None, *args):
        q = self.ent_query.get_text().strip()
        if not q:
            return
        self.discovery_container.set_visible(False)
        self.lbl_active_filter.set_markup(f"Search Query: <b>{q}</b>")
        self.reset_banner.set_visible(True)
        self.spinner.start()
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        threading.Thread(target=self._async_search, args=(q,), daemon=True).start()

    def _async_search(self, query: str):
        results = radiobrowser.run_search(query)
        GLib.idle_add(self._apply_results, results)

    def reset_discovery_view(self, button=None):
        self.reset_banner.set_visible(False)
        self.ent_query.set_text("")
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        self.discovery_container.set_visible(True)

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
