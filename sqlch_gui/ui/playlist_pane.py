"""Playlist pane: the queue, the RADIO / MEDIA toggle, drag in and reorder.

Reads queue.json directly (the daemon is the only writer) and sends every
change as a daemon command."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from sqlch.core import playqueue

from .. import daemon
from . import dnd
from .playlist_math import insert_index, move_target
from .source_pane import _thread_run
from .timefmt import format_duration


class PlaylistPane(Gtk.Box):
    def __init__(self, parent_window, read=playqueue.read, send=None,
                 run_async=_thread_run, watch=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.win = parent_window
        self._read = read
        self._send = send or (lambda msg: daemon.send(msg))
        self._run = run_async
        self._sig = None
        self._entries: list[dict] = []        # the entries behind the list rows, in order
        self._row_widgets: list[Gtk.Widget] = []
        self._remove_buttons: dict[str, Gtk.Button] = {}

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_radio = Gtk.ToggleButton(label="RADIO")
        self.btn_media = Gtk.ToggleButton(label="MEDIA")
        self.btn_media.set_group(self.btn_radio)
        for mode, button in (("radio", self.btn_radio), ("media", self.btn_media)):
            button.add_css_class("section-pill")
            button.set_tooltip_text("What next/prev and the media keys walk")
            # clicked, not toggled: syncing the buttons from the file must not send
            button.connect("clicked", lambda _b, m=mode: self._pick_mode(m))
            head.append(button)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        head.append(spacer)
        self.btn_clear = Gtk.Button(label="Clear")
        self.btn_clear.add_css_class("row-btn")
        self.btn_clear.connect("clicked", lambda _b: self._call({"cmd": "queue_clear"}))
        head.append(self.btn_clear)
        self.append(head)

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
        hint = Gtk.Label(label="Drag stations or tracks here")
        hint.add_css_class("meta-genre")
        self.list.set_placeholder(hint)
        drop = Gtk.DropTarget.new(GObject.TYPE_STRING,
                                  Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop)
        self.list.add_controller(drop)
        scroll.set_child(self.list)
        self.append(scroll)

        self._monitor = None
        if watch:
            f = Gio.File.new_for_path(str(playqueue.path()))
            self._monitor = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", lambda *_: GLib.idle_add(self.refresh))
        self.refresh()

    def on_shown(self):
        self.refresh()

    # --- state -> widgets ---

    def refresh(self) -> bool:
        state = self._read()
        # While media plays the resume position moves every few seconds;
        # it only shows (and only matters here) while parked.
        parked = state["resume"] if state["mode"] == "radio" else None
        now = state["now"]
        sig = (state["mode"], now and now["uid"],
               tuple(e["uid"] for e in state["entries"]),
               parked and (parked["entry"]["uid"], int(parked["pos"])))
        if sig == self._sig:
            return False
        self._sig = sig
        (self.btn_radio if state["mode"] == "radio" else self.btn_media).set_active(True)
        self._fill(state)
        self._show_resume(parked)
        return False

    def _fill(self, state):
        while row := self.list.get_first_child():
            self.list.remove(row)
        self._entries = list(state["entries"])
        self._row_widgets = []
        self._remove_buttons = {}
        if state["now"]:
            self.list.append(self._build_row(state["now"], now=True))
        for e in self._entries:
            row = self._build_row(e)
            self._row_widgets.append(row)
            self.list.append(row)

    def _show_resume(self, parked):
        if parked is None:
            self.status.set_visible(False)
            return
        title = playqueue.entry_title(parked["entry"])
        self.status.set_text(f"resume: {title}, {format_duration(parked['pos'])}")
        self.status.set_visible(True)

    def _build_row(self, entry, now=False):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("station-row")
        mark = Gtk.Label(label="▶" if now else ("◉" if entry["kind"] == "station" else ""))
        mark.add_css_class("meta-genre")
        mark.set_width_chars(2)
        row.append(mark)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        body.set_hexpand(True)
        title = Gtk.Label(label=playqueue.entry_title(entry), xalign=0.0)
        title.set_ellipsize(3)
        body.append(title)
        sub_text = playqueue.entry_subtitle(entry)
        sub = Gtk.Label(label=sub_text, xalign=0.0)
        sub.add_css_class("station-live")
        sub.set_ellipsize(3)
        sub.set_visible(bool(sub_text))
        body.append(sub)
        row.append(body)
        if not now:
            remove = Gtk.Button(label="✕")
            remove.add_css_class("row-btn")
            remove.set_valign(Gtk.Align.CENTER)
            remove.set_tooltip_text("Remove from the playlist")
            remove.connect("clicked", lambda _b, e=entry: self._call(
                {"cmd": "queue_remove", "uid": e["uid"]}))
            row.append(remove)
            self._remove_buttons[entry["uid"]] = remove
            click = Gtk.GestureClick()
            click.set_button(Gdk.BUTTON_PRIMARY)
            click.connect("released", lambda _g, _n, _x, _y, e=entry: self._play(e))
            row.add_controller(click)
            dnd.attach_drag(row, {"move": entry["uid"]})
        return row

    # --- commands ---

    def _call(self, msg):
        self._run(lambda: self._send(msg), self._done)

    def _done(self, resp, err):
        problem = err if err is not None else (
            "daemon not running" if resp is None
            else None if resp.get("ok", True) else resp.get("error") or "daemon refused")
        if problem is not None:
            self.status.set_text(f"Couldn't do that: {problem}")
            self.status.set_visible(True)
        else:
            GLib.idle_add(self.refresh)
        return False

    def _pick_mode(self, mode):
        self._call({"cmd": "set_mode", "mode": mode})

    def _play(self, entry):
        self._call({"cmd": "queue_play", "uid": entry["uid"]})

    # --- drag and drop ---

    def _midpoints(self) -> list[float]:
        mids = []
        for widget in self._row_widgets:
            ok, rect = widget.compute_bounds(self.list)
            if ok:
                mids.append(rect.get_y() + rect.get_height() / 2)
        return mids

    def _on_drop(self, _target, value, _x, y) -> bool:
        data = dnd.decode(value)
        if data is None:
            return False
        drop = insert_index(self._midpoints(), y)
        if "move" in data:
            uids = [e["uid"] for e in self._entries]
            if data["move"] not in uids:
                return False
            msg = {"cmd": "queue_move", "uid": data["move"],
                   "to": move_target(uids.index(data["move"]), drop)}
        else:
            msg = {"cmd": "queue_add", "kind": data["kind"],
                   "payload": data["payload"], "at": drop}
        self._call(msg)
        return True
