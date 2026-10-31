"""Drag payloads between panes. A tagged JSON string, so a stray text drop
onto the Playlist is ignored instead of queued."""

import json

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GObject, Gtk

PREFIX = "sqlch-queue:"


def encode(payload: dict) -> str:
    return PREFIX + json.dumps(payload)


def decode(text) -> dict | None:
    """A {"move": uid} reorder, or {"kind": "item"|"station", "payload": {...}}."""
    if not isinstance(text, str) or not text.startswith(PREFIX):
        return None
    try:
        data = json.loads(text[len(PREFIX):])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if "move" in data:
        return data if isinstance(data["move"], str) else None
    if data.get("kind") in ("item", "station") and isinstance(data.get("payload"), dict):
        return data
    return None


def station_payload(station: dict) -> dict:
    return {"id": station.get("id"), "name": station.get("name"), "url": station.get("url")}


def queue_msg(kind: str, payload: dict, play_next: bool = False) -> dict:
    return {"cmd": "queue_add", "kind": kind, "payload": payload, "play_next": play_next}


def attach_drag(widget, payload: dict) -> None:
    """Make `widget` a drag source carrying `payload`."""
    value = GObject.Value()
    value.init(GObject.TYPE_STRING)
    value.set_string(encode(payload))
    source = Gtk.DragSource()
    source.set_actions(Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
    source.connect("prepare", lambda _s, _x, _y: Gdk.ContentProvider.new_for_value(value))
    widget.add_controller(source)
