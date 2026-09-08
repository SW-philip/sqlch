"""Network Radio-Browser directory scanning interface."""

import html
import threading
from gi.repository import Gtk, GLib
from .. import radiobrowser
from .. import library
from .banner import RibbonBanner, PennantTag

GENRE_TAGS = ["Jazz", "News", "Rock", "Electronic", "Classical", "Talk", "Ambient", "Sports", "80s"]


class DiscoverPanel(Gtk.Box):
    def __init__(self, parent_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.win = parent_window
        self._results: list[dict] = []
        self._active_term = ""
        self._active_kind = "name"   # "name" | "tag"
        self._page_size = 25
        self._search_gen = 0
        self._load_more_row: Gtk.Widget | None = None

        # Execution query controls
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.ent_query = Gtk.Entry(placeholder_text="Search worldwide directory...")
        self.ent_query.set_hexpand(True)
        self.ent_query.add_css_class("field-entry")
        self.ent_query.connect("activate", self.on_search)

        btn_go = Gtk.Button(icon_name="edit-find-symbolic")
        btn_go.add_css_class("search-btn")
        btn_go.connect("clicked", self.on_search)

        search_box.append(self.ent_query)
        search_box.append(btn_go)
        self.append(search_box)

        # Scoped Container for Category Discovery
        self.discovery_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.browse_title = RibbonBanner("Browse Categories", gold=True)
        self.discovery_container.append(self.browse_title)

        # Genre browse grid
        self.tag_grid = Gtk.FlowBox()
        self.tag_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.tag_grid.set_max_children_per_line(4)
        self.tag_grid.set_row_spacing(4)
        self.tag_grid.set_column_spacing(4)
        for tag in GENRE_TAGS:
            btn = Gtk.Button()
            btn.set_child(PennantTag(tag.lower()))
            btn.add_css_class("pennant-btn")
            btn.connect("clicked", lambda b, t=tag: self.on_tag_clicked(t))
            self.tag_grid.append(btn)
        self.discovery_container.append(self.tag_grid)
        self.append(self.discovery_container)

        # Reset active selection banner
        self.reset_banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
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
        self.results_box.set_vexpand(True)
        scroll.set_child(self.results_box)
        self.append(scroll)

        self.spinner = Gtk.Spinner()
        self.append(self.spinner)

    def _start_search(self, kind: str, term: str):
        self._search_gen += 1
        self._results = []
        self._active_kind = kind
        self._active_term = term
        self._load_more_row = None

        self.discovery_container.set_visible(False)
        label = "Search Query" if kind == "name" else "Active Genre"
        self.lbl_active_filter.set_markup(
            f"{label}: <b>{html.escape(term)}</b>"
        )
        self.reset_banner.set_visible(True)
        self.spinner.start()
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)

        gen = self._search_gen
        threading.Thread(
            target=self._fetch_page, args=(gen, 0), daemon=True
        ).start()

    def on_tag_clicked(self, tag: str):
        self._start_search("tag", tag)

    def on_search(self, button=None, *args):
        q = self.ent_query.get_text().strip()
        if not q:
            return
        self._start_search("name", q)

    def _fetch_page(self, gen: int, offset: int):
        if self._active_kind == "name":
            results = radiobrowser.search(self._active_term, offset=offset)
        else:
            results = radiobrowser.search_by_tag(
                self._active_term, offset=offset
            )
        GLib.idle_add(self._apply_page, gen, offset, results)

    def reset_discovery_view(self, button=None):
        self.reset_banner.set_visible(False)
        self.ent_query.set_text("")
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)
        self._results = []
        self._active_term = ""
        self._load_more_row = None
        self.discovery_container.set_visible(True)

    def _build_row(self, r: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.set_margin_top(3)
        row.set_margin_bottom(3)

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        meta.set_hexpand(True)

        title = Gtk.Label(label=r["name"], xalign=0.0)
        title.set_ellipsize(3)

        sub = Gtk.Label(xalign=0.0)
        sub.add_css_class("meta-genre")
        sub.set_text(r.get("tags", "")[:40])

        meta.append(title)
        meta.append(sub)
        row.append(meta)

        cc = r.get("country", "")
        if cc:
            cc_tag = PennantTag(cc, country=True)
            cc_tag.set_valign(Gtk.Align.CENTER)
            row.append(cc_tag)

        bitrate = r.get("bitrate")
        if bitrate:
            rate_lbl = Gtk.Label(label=f"{bitrate}k")
            rate_lbl.add_css_class("small-badge")
            rate_lbl.set_valign(Gtk.Align.CENTER)
            row.append(rate_lbl)

        btn_import = Gtk.Button(icon_name="bookmark-new-symbolic")
        btn_import.set_tooltip_text("Import into local station library")
        btn_import.connect("clicked", lambda b, st=r: self.on_import(st))
        row.append(btn_import)
        return row

    def _apply_page(
        self, gen: int, offset: int, results: list[dict]
    ) -> bool:
        if gen != self._search_gen:
            return False
        self.spinner.stop()

        if self._load_more_row is not None:
            self.results_box.remove(self._load_more_row)
            self._load_more_row = None

        if offset == 0 and not results:
            lbl = Gtk.Label(label="No stations matched query parameters.")
            lbl.set_margin_top(12)
            self.results_box.append(lbl)
            return False

        for r in results:
            self.results_box.append(self._build_row(r))
        self._results.extend(results)

        if len(results) == self._page_size:
            self._load_more_row = self._build_load_more()
            self.results_box.append(self._load_more_row)
        return False

    def _build_load_more(self) -> Gtk.Button:
        btn = Gtk.Button(label=f"Load {self._page_size} more")
        btn.add_css_class("load-more-row")
        btn.set_hexpand(True)
        btn.connect("clicked", self._on_load_more)
        return btn

    def _on_load_more(self, button: Gtk.Button):
        button.set_sensitive(False)
        button.set_label("Loading…")
        gen = self._search_gen
        threading.Thread(
            target=self._fetch_page,
            args=(gen, len(self._results)),
            daemon=True,
        ).start()

    def on_import(self, station: dict):
        err = library.add_url(station["name"], station["url"])
        if not err and self.win:
            self.win.trigger_library_refresh()
