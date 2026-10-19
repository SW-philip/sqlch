"""Generic dock pane for a media source: browse folders, search, play items."""

import threading

from gi.repository import Gtk, GLib

from sqlch.core import follows
from sqlch.sources import safe_available, sections_for

from .. import daemon
from .timefmt import format_duration


def _thread_run(work, done):
    def run():
        try:
            result, err = work(), None
        except Exception as e:
            result, err = None, str(e)
        GLib.idle_add(done, result, err)

    threading.Thread(target=run, daemon=True).start()


class SourcePane(Gtk.Box):
    def __init__(self, parent_window, source, run_async=_thread_run, play=None,
                 store=None, send=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.win = parent_window
        self.source = source
        self._run = run_async
        self._play = play or self._daemon_play
        self._items: list[dict] = []
        self._stack: list[tuple] = []
        self._searching = False
        self._gen = 0
        self._loaded = False
        self._pending = None
        self._play_error = False
        self._store = store or follows
        self._send = send or (lambda msg: daemon.send(msg))
        self._sections = sections_for(source)
        self._section = self._sections[0]["id"]
        self._fav_ids: set = set()
        self._followed: set = set()

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.entry = Gtk.Entry(placeholder_text=f"Search {source.NAME}...")
        self.entry.set_hexpand(True)
        self.entry.add_css_class("field-entry")
        self.entry.connect("activate", lambda e: self._search(e.get_text().strip()))
        btn_go = Gtk.Button(icon_name="edit-find-symbolic")
        btn_go.add_css_class("search-btn")
        btn_go.connect("clicked", lambda b: self._search(self.entry.get_text().strip()))
        search_box.append(self.entry)
        search_box.append(btn_go)
        self.append(search_box)

        self.section_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._pills: dict[str, Gtk.Button] = {}
        for sec in self._sections:
            pill = Gtk.Button(label=sec["title"])
            pill.add_css_class("section-pill")
            pill.connect("clicked", lambda _b, sid=sec["id"]: self._select_section(sid))
            self.section_row.append(pill)
            self._pills[sec["id"]] = pill
        self._mark_pills()
        self.append(self.section_row)

        self.nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.nav.set_visible(False)
        btn_back = Gtk.Button(icon_name="go-previous-symbolic")
        btn_back.add_css_class("control-btn")
        btn_back.connect("clicked", lambda b: self.back())
        self.crumb = Gtk.Label(xalign=0.0)
        self.crumb.add_css_class("meta-genre")
        self.crumb.set_ellipsize(3)
        self.crumb.set_hexpand(True)
        self.nav.append(btn_back)
        self.nav.append(self.crumb)
        self.append(self.nav)

        self.status = Gtk.Label(xalign=0.0)
        self.status.add_css_class("meta-genre")
        self.status.set_wrap(True)
        self.status.set_visible(False)
        self.append(self.status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list = Gtk.ListBox()
        self.list.add_css_class("list-plate")
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list.set_vexpand(True)
        scroll.set_child(self.list)
        self.append(scroll)

    @staticmethod
    def _daemon_play(item):
        resp = daemon.send({"cmd": "play_item", "item": item})
        if resp is None:
            raise RuntimeError("daemon not running")
        if not resp.get("ok", True):
            raise RuntimeError(resp.get("error") or "daemon refused")

    def on_shown(self):
        if self._loaded:
            if self._pending is not None:
                self._load(self._pending)
            return
        self._loaded = True
        if not safe_available(self.source):
            self._set_status(self.source.HINT)
            return
        self._reload()

    def on_hidden(self):
        self._gen += 1

    def _set_status(self, text, play_error=False):
        self._play_error = play_error and bool(text)
        self.status.set_text(text)
        self.status.set_visible(bool(text))

    def _current_path(self):
        if self._stack:
            return self._stack[-1][0]
        if self._section == "browse":
            return None
        return f"section:{self._section}"

    def _mark_pills(self):
        for sid, pill in self._pills.items():
            if sid == self._section:
                pill.add_css_class("active")
            else:
                pill.remove_css_class("active")

    def _select_section(self, sid):
        self._section = sid
        self._stack = []
        self._searching = False
        self.entry.set_text("")
        self._mark_pills()
        self._reload()

    def _browse(self, path):
        if path == "section:favorites":
            return self._store.list_favorites(self.source.NAME)
        return self.source.browse(path)

    def _reload(self):
        self._load(lambda: self._browse(self._current_path()))

    def _with_marks(self, work):
        """Also refresh star/follow state; runs in the worker with the load."""
        def run():
            result = work()
            self._fav_ids = self._store.favorite_ids(self.source.NAME)
            self._followed = self._store.followed_ids()
            return result
        return run

    def _load(self, work):
        self._gen += 1
        gen = self._gen
        self._pending = work
        self._update_nav()
        self._run(self._with_marks(work), lambda result, err: self._show(gen, result, err))

    def _show(self, gen, result, err):
        if gen != self._gen:
            return False
        self._pending = None
        while child := self.list.get_first_child():
            self.list.remove(child)
        if err is not None:
            self._items = []
            self._set_status(f"Couldn't load: {err}")
            return False
        self._items = list(result or [])
        for item in self._items:
            self.list.append(self._build_row(item))
        self._set_status("" if self._items else "Nothing here")
        return False

    def _update_nav(self):
        self.nav.set_visible(bool(self._stack) or self._searching)
        if self._searching:
            self.crumb.set_text("Search results")
        else:
            self.crumb.set_text(" / ".join(t for _, t in self._stack))

    def _build_row(self, item):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.add_css_class("station-row")
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.set_hexpand(True)
        title = Gtk.Label(label=item.get("title", ""), xalign=0.0)
        title.set_ellipsize(3)
        body.append(title)
        sub_text = " · ".join(x for x in (item.get("artist"), item.get("album")) if x)
        sub = Gtk.Label(label=sub_text, xalign=0.0)
        sub.add_css_class("station-live")
        sub.set_ellipsize(3)
        sub.set_visible(bool(sub_text))
        body.append(sub)
        row.append(body)
        right = "›" if item.get("kind") == "folder" else format_duration(item.get("duration"))
        end = Gtk.Label(label=right, xalign=1.0)
        end.add_css_class("meta-genre")
        end.set_valign(Gtk.Align.CENTER)
        row.append(end)
        star = Gtk.Button(label="★" if item.get("id") in self._fav_ids else "☆")
        star.add_css_class("row-btn")
        star.set_valign(Gtk.Align.CENTER)
        star.connect("clicked", lambda b, it=item: self._toggle_favorite(it, b))
        row.append(star)
        if item.get("channel_id"):
            following = item["channel_id"] in self._followed
            fol = Gtk.Button(label="Unfollow" if following else "Follow")
            fol.add_css_class("row-btn")
            fol.set_valign(Gtk.Align.CENTER)
            fol.connect("clicked", lambda b, it=item: self._toggle_follow(it, b))
            row.append(fol)
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", lambda g, n, x, y, it=item: self._activate(it))
        row.add_controller(click)
        return row

    def _activate(self, item):
        if item.get("kind") == "folder":
            self._stack.append((item["path"], item["title"]))
            self._searching = False
            self._reload()
        else:
            self._run(lambda: self._play(item), self._played)

    def _played(self, result, err):
        if err is not None:
            self._set_status(f"Couldn't play: {err}", play_error=True)
        elif self._play_error:
            self._set_status("")
        return False

    def _toggle_favorite(self, item, button):
        def done(result, err):
            resp = result or {}
            if err is not None or not resp.get("ok"):
                self._set_status("Couldn't update favorites: "
                                 f"{err or resp.get('error') or 'daemon not running'}")
                return False
            if resp["favorite"]:
                self._fav_ids.add(item["id"])
            else:
                self._fav_ids.discard(item["id"])
            button.set_label("★" if resp["favorite"] else "☆")
            if (self._section == "favorites" and not self._stack
                    and not self._searching and not resp["favorite"]):
                self._reload()
            return False

        self._run(lambda: self._send({"cmd": "toggle_favorite", "item": item}), done)

    def _toggle_follow(self, item, button):
        cid = item["channel_id"]
        following = cid in self._followed
        if following:
            msg = {"cmd": "unfollow", "channel_id": cid}
        else:
            name = item["title"] if item.get("kind") == "folder" else item.get("artist")
            msg = {"cmd": "follow", "channel_id": cid, "name": name or cid}

        def done(result, err):
            resp = result or {}
            if err is not None or not resp.get("ok"):
                self._set_status("Couldn't update follows: "
                                 f"{err or resp.get('error') or 'daemon not running'}")
                return False
            if following:
                self._followed.discard(cid)
            else:
                self._followed.add(cid)
            button.set_label("Follow" if following else "Unfollow")
            if following and self._section == "channels" and not self._stack \
                    and not self._searching:
                self._reload()
            return False

        self._run(lambda: self._send(msg), done)

    def back(self):
        if self._searching:
            self.entry.set_text("")
            self._searching = False
        elif self._stack:
            self._stack.pop()
        self._reload()

    def _search(self, query):
        if not query:
            self.entry.set_text("")
            self._searching = False
            self._reload()
            return
        self._searching = True
        self._load(lambda: self.source.search(query))
