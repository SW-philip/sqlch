"""Generic dock pane for a media source: browse folders, search, play items."""

import threading
from concurrent.futures import ThreadPoolExecutor

from gi.repository import Gtk, GLib

from sqlch.core import follows, progress as watch_progress
from sqlch.sources import safe_available, sections_for

from .. import daemon
from .banner import RibbonBanner
from .grouping import LABELS, group, next_mode
from .timefmt import format_date, format_duration
from .tooltips import item_tooltip

_THUMBS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="thumb")


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
                 store=None, send=None, watch=None):
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
        self._watch = watch or watch_progress
        self._progress: dict = {}
        self._row_refs: dict = {}
        self._fav_btns: dict[str, list[Gtk.Button]] = {}
        self._follow_btns: dict[str, list[Gtk.Button]] = {}
        self._oldest_first = False
        self._groupings = tuple(getattr(source, "GROUPINGS", ()) or ())
        self._group_mode = self._groupings[0] if self._groupings else None
        self._collapsed: set = set()
        self._group_rows: list = []

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
        self.btn_order = None
        if getattr(source, "HAS_DATES", False):
            self.btn_order = Gtk.ToggleButton(label="Oldest first")
            self.btn_order.add_css_class("section-pill")
            self.btn_order.connect("toggled", self._on_order_toggled)
            search_box.append(self.btn_order)
        self.btn_group = None
        if self._groupings:
            self.btn_group = Gtk.Button(label=LABELS.get(self._group_mode, self._group_mode))
            self.btn_group.add_css_class("section-pill")
            self.btn_group.set_tooltip_text("Group by")
            self.btn_group.connect("clicked", self._on_group_clicked)
            search_box.append(self.btn_group)
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
    def _daemon_play(item, resume=False):
        resp = daemon.send({"cmd": "play_item", "item": item, "resume": resume})
        if resp is None:
            raise RuntimeError("daemon not running")
        if not resp.get("ok", True):
            raise RuntimeError(resp.get("error") or "daemon refused")

    def on_shown(self):
        if self._loaded:
            if self._pending is not None:
                self._load(self._pending)
            else:
                self._refresh_progress()
            return
        self._loaded = True
        if not safe_available(self.source):
            self.section_row.set_visible(False)
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
        """Read star/follow state and any source warning in the worker; _show
        applies them on the main thread."""
        def run():
            result = work()
            warn = getattr(self.source, "last_warning", None)
            return (result, set(self._store.favorite_ids(self.source.NAME)),
                    set(self._store.followed_ids()) | set(self._store.followed_feeds()),
                    warn() if warn else None)
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
        warning = None
        if err is None:
            result, self._fav_ids, self._followed, warning = result
        while child := self.list.get_first_child():
            self.list.remove(child)
        if err is not None:
            self._items = []
            self._set_status(f"Couldn't load: {err}")
            return False
        self._items = list(result or [])
        self._progress = self._watch.read_all()
        self._collapsed = set()
        self._fill()
        self._set_status(warning or ("" if self._items else "Nothing here"))
        return False

    def _fill(self):
        while child := self.list.get_first_child():
            self.list.remove(child)
        self._row_refs = {}
        self._fav_btns = {}
        self._follow_btns = {}
        self._group_rows = []
        grouped = self._grouped()
        if self.btn_group is not None:
            self.btn_group.set_visible(grouped)
        if self.btn_order is not None:
            self.btn_order.set_visible(not grouped)
        if grouped:
            self._fill_grouped()
            return
        items = self._items
        if self._oldest_first:
            # Stable: undated rows (folders) keep their place after the dated ones.
            items = sorted(items, key=lambda i: (i.get("date") is None, i.get("date") or 0))
        for item in items:
            self.list.append(self._build_row(item))

    def _grouped(self):
        return bool(self._groupings) and (
            self._searching or (not self._stack and self._section != "favorites"))

    def _fill_grouped(self):
        path: list[str] = []
        providers = getattr(self.source, "PROVIDERS", None) or {}
        for kind, value, extra in group(self._items, self._group_mode, providers):
            if kind == "header":
                del path[extra:]
                path.append(value)
                key = "/".join(path)
                banner = RibbonBanner(value, gold=extra == 0, collapsible=True,
                                      collapsed=key in self._collapsed,
                                      on_toggle=lambda c, k=key: self._toggle_group(k, c))
                if extra:
                    banner.set_margin_start(10 * extra)
                self.list.append(banner)
                self._group_rows.append((banner, extra, key))
            else:
                row = self._build_row(value, tag=extra)
                self.list.append(row)
                self._group_rows.append((row, None, None))
        self._apply_collapse()

    def _toggle_group(self, key, collapsed):
        if collapsed:
            self._collapsed.add(key)
        else:
            self._collapsed.discard(key)
        self._apply_collapse()

    def _apply_collapse(self):
        hidden_below = None  # depth of the collapsed header hiding what follows
        for widget, depth, key in self._group_rows:
            if depth is not None and hidden_below is not None and depth <= hidden_below:
                hidden_below = None
            (widget.get_parent() or widget).set_visible(hidden_below is None)
            if depth is not None and hidden_below is None and key in self._collapsed:
                hidden_below = depth

    def _on_group_clicked(self, button):
        self._group_mode = next_mode(self._group_mode, self._groupings)
        button.set_label(LABELS.get(self._group_mode, self._group_mode))
        self._fill()

    def _on_order_toggled(self, button):
        self._oldest_first = button.get_active()
        self._fill()

    def _refresh_progress(self):
        self._progress = self._watch.read_all()
        for key in self._row_refs:
            self._apply_progress(key)

    def _apply_progress(self, key):
        refs = self._row_refs.get(key)
        if not refs:
            return
        row = self._progress.get(key)
        row = row if isinstance(row, dict) else None
        watched = bool(row and row.get("watched"))
        frac = watch_progress.fraction(row)
        refs["banner"].set_visible(watched)
        refs["bar"].set_fraction(frac)
        refs["bar"].set_visible(not watched and frac > 0)
        pos = watch_progress.resume_point(row)
        if watched:
            note = "Watched"
        elif pos is not None:
            note = f"{format_duration(pos)} of {format_duration(row.get('duration'))} watched"
        else:
            note = ""
        refs["note"].set_text(note)
        refs["note"].set_visible(bool(note))
        refs["toggle"].set_label("✓" if watched else "○")

    def _update_nav(self):
        self.nav.set_visible(bool(self._stack) or self._searching)
        if self._searching:
            self.crumb.set_text("Search results")
        else:
            self.crumb.set_text(" / ".join(t for _, t in self._stack))

    def _build_row(self, item, tag=None):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.add_css_class("station-row")
        is_video = item.get("kind") == "video"
        key = watch_progress.key(item.get("source", ""), item.get("id", ""))
        if is_video:
            thumb, banner = self._build_thumb(item)
            row.append(thumb)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.set_hexpand(True)
        title = Gtk.Label(label=item.get("title", ""), xalign=0.0)
        title.set_ellipsize(3)
        body.append(title)
        sub_text = " · ".join(x for x in (item.get("artist"), item.get("album"),
                                          format_date(item.get("date")), tag) if x)
        sub = Gtk.Label(label=sub_text, xalign=0.0)
        sub.add_css_class("station-live")
        sub.set_ellipsize(3)
        sub.set_visible(bool(sub_text))
        body.append(sub)
        if is_video:
            note = Gtk.Label(xalign=0.0)
            note.add_css_class("station-live")
            note.set_visible(False)
            body.append(note)
            bar = Gtk.ProgressBar()
            bar.add_css_class("watch-bar")
            bar.set_visible(False)
            body.append(bar)
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
        self._fav_btns.setdefault(item.get("id"), []).append(star)
        if is_video:
            toggle = Gtk.Button(label="○")
            toggle.add_css_class("row-btn")
            toggle.set_valign(Gtk.Align.CENTER)
            toggle.set_tooltip_text("Mark watched / unwatched")
            toggle.connect("clicked", lambda b, it=item: self._toggle_watched(it))
            row.append(toggle)
            self._row_refs[key] = {"banner": banner, "bar": bar,
                                   "note": note, "toggle": toggle}
            self._apply_progress(key)
        follow_key = item.get("channel_id") or item.get("feed_url")
        if follow_key:
            following = follow_key in self._followed
            fol = Gtk.Button(label="Unfollow" if following else "Follow")
            fol.add_css_class("row-btn")
            fol.set_valign(Gtk.Align.CENTER)
            fol.connect("clicked", lambda b, it=item: self._toggle_follow(it, b))
            row.append(fol)
            self._follow_btns.setdefault(follow_key, []).append(fol)
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("released", lambda g, n, x, y, it=item, r=row: self._activate(it, r))
        row.add_controller(click)
        row.set_tooltip_text(item_tooltip(item))
        return row

    def _build_thumb(self, item):
        pic = Gtk.Picture()
        pic.set_size_request(96, 54)
        pic.set_can_shrink(True)
        pic.set_content_fit(Gtk.ContentFit.COVER)
        pic.add_css_class("thumb")
        banner = Gtk.Label(label="WATCHED")
        banner.add_css_class("corner-tag")
        banner.add_css_class("corner-tag-right")
        banner.add_css_class("thumb-tag")
        banner.set_halign(Gtk.Align.END)
        banner.set_valign(Gtk.Align.END)
        banner.set_visible(False)
        overlay = Gtk.Overlay()
        overlay.set_child(pic)
        overlay.add_overlay(banner)
        overlay.set_valign(Gtk.Align.CENTER)
        thumbnail = getattr(self.source, "thumbnail", None)
        if thumbnail is not None:
            _THUMBS.submit(self._load_thumb, thumbnail, item, pic)
        return overlay, banner

    @staticmethod
    def _load_thumb(thumbnail, item, pic):
        try:
            path = thumbnail(item)
        except Exception:
            return
        if path:
            GLib.idle_add(pic.set_filename, path)

    def _activate(self, item, anchor=None):
        if item.get("kind") == "folder":
            self._stack.append((item["path"], item["title"]))
            self._searching = False
            self._reload()
            return
        point = None
        if item.get("kind") == "video":
            point = watch_progress.resume_point(self._watch.get(item["source"], item["id"]))
        if point is not None and anchor is not None:
            self._offer_resume(item, point, anchor)
        else:
            self._run(lambda: self._play(item), self._played)

    def _offer_resume(self, item, point, anchor):
        pop = Gtk.Popover()
        pop.set_parent(anchor)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for label, resume in ((f"Resume from {format_duration(point)}", True),
                              ("Start over", False)):
            btn = Gtk.Button(label=label)
            btn.add_css_class("row-btn")
            btn.connect("clicked", lambda b, r=resume, p=pop: self._start(item, r, p))
            box.append(btn)
        pop.set_child(box)
        pop.popup()

    def _start(self, item, resume, pop):
        pop.popdown()
        if resume:
            self._run(lambda: self._play(item, resume=True), self._played)
        else:
            self._run(lambda: self._play(item), self._played)

    def _toggle_watched(self, item):
        key = watch_progress.key(item["source"], item["id"])
        row = self._progress.get(key)
        watched = not bool(isinstance(row, dict) and row.get("watched"))
        msg = {"cmd": "mark_watched", "item": item, "watched": watched}

        def done(result, err):
            resp = result or {}
            if err is not None or not resp.get("ok"):
                self._set_status("Couldn't update watched: "
                                 f"{err or resp.get('error') or 'daemon not running'}")
            else:
                self._refresh_progress()
            return False

        self._run(lambda: self._send(msg), done)

    def _played(self, result, err):
        if err is not None:
            self._set_status(f"Couldn't play: {err}", play_error=True)
        elif self._play_error:
            self._set_status("")
        return False

    @staticmethod
    def _buttons(index, key, button):
        """The clicked button plus every row's twin for the same key."""
        found = list(index.get(key, []))
        return found if any(b is button for b in found) else found + [button]

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
            for b in self._buttons(self._fav_btns, item["id"], button):
                b.set_label("★" if resp["favorite"] else "☆")
            if (self._section == "favorites" and not self._stack
                    and not self._searching and not resp["favorite"]):
                self._reload()
            return False

        self._run(lambda: self._send({"cmd": "toggle_favorite", "item": item}), done)

    def _toggle_follow(self, item, button):
        key = item.get("channel_id") or item["feed_url"]
        following = key in self._followed
        if item.get("channel_id"):
            if following:
                msg = {"cmd": "unfollow", "channel_id": key}
            else:
                name = item["title"] if item.get("kind") == "folder" else item.get("artist")
                msg = {"cmd": "follow", "channel_id": key, "name": name or key}
        elif following:
            msg = {"cmd": "podcast_unfollow", "feed_url": key}
        else:
            msg = {"cmd": "podcast_follow", "item": item}

        def done(result, err):
            resp = result or {}
            if err is not None or not resp.get("ok"):
                self._set_status("Couldn't update follows: "
                                 f"{err or resp.get('error') or 'daemon not running'}")
                return False
            if following:
                self._followed.discard(key)
            else:
                self._followed.add(key)
            for b in self._buttons(self._follow_btns, key, button):
                b.set_label("Follow" if following else "Unfollow")
            if following and self._section in ("channels", "following") \
                    and not self._stack and not self._searching:
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
