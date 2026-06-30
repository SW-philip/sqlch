"""Network Radio-Browser directory scanning interface."""

import threading
from gi.repository import Gtk, GLib
from .. import radiobrowser

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

    def on_search(self, widget):
        q = self.ent_query.get_text().strip()
        if not q:
            return
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