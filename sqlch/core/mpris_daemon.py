"""
SQLCH MPRIS daemon
------------------
- Polls MPV via IPC socket for ICY stream metadata
- Enriches track info via sqlch.core.enrich (Spotify + MusicBrainz)
- Publishes playback state as org.mpris.MediaPlayer2.sqlch on the session D-Bus
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from gi.repository import GLib
from pydbus import SessionBus
from pydbus.generic import signal

from sqlch.core import enrich
from sqlch.core.player import mpv_socket

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUS_NAME = "org.mpris.MediaPlayer2.sqlch"
OBJ_PATH = "/org/mpris/MediaPlayer2"

MPRIS_XML = """
<node>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg type="s" direction="in"/>
      <arg type="s" direction="in"/>
      <arg type="v" direction="out"/>
    </method>
    <method name="Set">
      <arg type="s" direction="in"/>
      <arg type="s" direction="in"/>
      <arg type="v" direction="in"/>
    </method>
    <method name="GetAll">
      <arg type="s" direction="in"/>
      <arg type="a{sv}" direction="out"/>
    </method>
    <signal name="PropertiesChanged">
      <arg type="s"/>
      <arg type="a{sv}"/>
      <arg type="as"/>
    </signal>
  </interface>

  <interface name="org.mpris.MediaPlayer2">
    <property name="CanQuit"       type="b"  access="read"/>
    <property name="CanRaise"      type="b"  access="read"/>
    <property name="HasTrackList"  type="b"  access="read"/>
    <property name="Identity"      type="s"  access="read"/>
    <property name="DesktopEntry"  type="s"  access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes"  type="as" access="read"/>
    <method name="Raise"/>
    <method name="Quit"/>
  </interface>

  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Play"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <property name="PlaybackStatus" type="s"  access="read"/>
    <property name="Metadata"       type="a{sv}" access="read"/>
    <property name="Volume"         type="d"  access="readwrite"/>
    <property name="Position"       type="x"  access="read"/>
    <property name="CanControl"     type="b"  access="read"/>
    <property type="b" name="CanPlay"       access="read"/>
    <property type="b" name="CanPause"      access="read"/>
    <property type="b" name="CanSeek"       access="read"/>
    <property type="b" name="CanGoNext"     access="read"/>
    <property type="b" name="CanGoPrevious" access="read"/>
  </interface>
</node>
"""

# ---------------------------------------------------------------------------
# GLib variant helpers
# ---------------------------------------------------------------------------

def V(sig: str, value: Any) -> GLib.Variant:
    return GLib.Variant(sig, value)


def _to_variant(value: Any) -> GLib.Variant:
    """Best-effort conversion of a Python value to a GLib.Variant."""
    if isinstance(value, bool):
        return V("b", value)
    if isinstance(value, int):
        return V("x", value)
    if isinstance(value, float):
        return V("d", value)
    if isinstance(value, list):
        return V("as", value)
    return V("s", str(value))


def dict_to_a_sv(d: Dict[str, Any]) -> GLib.Variant:
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if k == "mpris:trackid":
            out[k] = V("o", v)
        else:
            out[k] = _to_variant(v)
    return V("a{sv}", out)


def wrap_metadata(meta: Dict[str, Any]) -> GLib.Variant:
    """
    Convert an MPRIS metadata dict to a GLib a{sv} Variant.
    Handles the special case of mpris:trackid (object path).
    """
    out: Dict[str, GLib.Variant] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if k == "mpris:trackid":
            out[k] = V("o", v)
        elif isinstance(v, list):
            out[k] = V("as", v)
        else:
            out[k] = V("s", str(v))
    return V("a{sv}", out)


# ---------------------------------------------------------------------------
# MPV IPC helpers
# ---------------------------------------------------------------------------

def _mpv_ipc(cmd: dict, timeout: float = 0.5) -> Optional[dict]:
    """Send a JSON command to the MPV IPC socket and return the response."""
    sock = mpv_socket()
    if not sock.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock))
            s.sendall((json.dumps(cmd) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        if buf.strip():
            return json.loads(buf.decode())
    except Exception:
        return None
    return None


def mpv_get(prop: str) -> Any:
    """Read a property from MPV. Returns None on failure."""
    r = _mpv_ipc({"command": ["get_property", prop]})
    if r and r.get("error") == "success":
        return r.get("data")
    return None


def mpv_cmd(*args: str) -> None:
    """Send a fire-and-forget command to MPV."""
    _mpv_ipc({"command": list(args)})


# ---------------------------------------------------------------------------
# ICY title parsing
# ---------------------------------------------------------------------------

def parse_icy_title(s: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse an ICY stream title into (artist, track).
    Handles 'Artist - Track', 'Artist-Track', and bare track titles.
    """
    if not s:
        return None, None
    if " - " in s:
        artist, track = s.split(" - ", 1)
    elif "-" in s:
        artist, track = s.split("-", 1)
    else:
        return None, s.strip()
    return artist.strip() or None, track.strip() or None


# ---------------------------------------------------------------------------
# MPRIS D-Bus object
# ---------------------------------------------------------------------------

class SQLCHMPRIS:
    """
    MPRIS2 MediaPlayer2 + Player interface for SQLCH radio streams.

    Bridges MPV (via IPC socket) and D-Bus, with enriched track metadata
    sourced from Spotify / MusicBrainz.
    """

    PropertiesChanged = signal()

    # --- MediaPlayer2 static properties ---
    CanQuit             = False
    CanRaise            = False
    HasTrackList        = False
    Identity            = "SQLCH"
    DesktopEntry        = "sqlch"
    SupportedUriSchemes = ["http", "https"]
    SupportedMimeTypes  = ["audio/mpeg", "audio/ogg", "audio/aac"]
    CanControl          = True
    CanPlay             = True
    CanPause            = True
    CanSeek             = False
    CanGoNext           = False
    CanGoPrevious       = False

    def __init__(self) -> None:
        self._playback_status: str = "Stopped"
        self._metadata: Dict[str, Any] = {}
        self._volume: float = 1.0
        self._last_icy: Optional[str] = None
        self._last_trackid: str = "/org/mpris/MediaPlayer2/Track/0"
        self._stop = threading.Event()

    # --- org.freedesktop.DBus.Properties ---

    def Get(self, interface: str, prop: str) -> GLib.Variant:
        if not hasattr(self, prop):
            return V("s", "")
        val = getattr(self, prop)
        if interface == "org.mpris.MediaPlayer2.Player" and prop == "Metadata":
            return dict_to_a_sv(val)
        return _to_variant(val)

    def Set(self, iface: str, prop: str, value: Any) -> None:
        if iface == "org.mpris.MediaPlayer2.Player" and prop == "Volume":
            self.Volume = float(value)
            return
        raise Exception("org.freedesktop.DBus.Error.PropertyReadOnly")

    def GetAll(self, interface: str) -> Dict[str, GLib.Variant]:
        props: Dict[str, GLib.Variant] = {}
        for attr in dir(self):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(self, attr)
            except Exception:
                continue
            if callable(val):
                continue
            if interface.endswith("Player") and attr == "Metadata":
                props[attr] = dict_to_a_sv(val)
            else:
                props[attr] = _to_variant(val)
        return props

    def Introspect(self):
        return MPRIS_XML

    # --- Player properties ---

    @property
    def PlaybackStatus(self) -> str:
        return self._playback_status

    @property
    def Metadata(self) -> Dict[str, Any]:
        return self._metadata

    @property
    def Volume(self) -> float:
        return self._volume

    @Volume.setter
    def Volume(self, v: float) -> None:
        self._volume = max(0.0, float(v))
        mpv_cmd("set_property", "volume", str(self._volume * 100))
        self._emit_changed({"Volume": V("d", self._volume)})

    @property
    def Position(self) -> int:
        t = mpv_get("playback-time")
        return int(float(t) * 1_000_000) if t is not None else 0

    # --- Player commands ---

    def Play(self) -> None:
        mpv_cmd("set_property", "pause", "no")
        self._set_status("Playing")

    def Pause(self) -> None:
        mpv_cmd("set_property", "pause", "yes")
        self._set_status("Paused")

    def Stop(self) -> None:
        mpv_cmd("quit")
        self._set_status("Stopped")

    def PlayPause(self) -> None:
        mpv_cmd("cycle", "pause")

    def Raise(self) -> None:
        pass

    def Quit(self) -> None:
        self._stop.set()

    # --- Internal helpers ---

    def _set_status(self, status: str) -> None:
        if status != self._playback_status:
            self._playback_status = status
            self._emit_changed({"PlaybackStatus": V("s", self._playback_status)})

    def _emit_changed(self, changed: Dict[str, GLib.Variant]) -> None:
        """Emit PropertiesChanged on the GLib main loop."""
        def _emit() -> bool:
            self.PropertiesChanged("org.mpris.MediaPlayer2.Player", changed, [])
            return False  # one-shot idle callback
        GLib.idle_add(_emit)

    def _update_metadata(self, station_name: str, icy_title: str) -> None:
        """
        Parse the ICY title, enrich via Spotify/MusicBrainz, and publish
        updated MPRIS metadata + PropertiesChanged signal.
        """
        artist, track = parse_icy_title(icy_title)
        if not track:
            return

        meta = enrich.enrich_track(artist or "", track)

        mpris_meta: Dict[str, Any] = {
            "mpris:trackid": self._last_trackid,
            "xesam:title":   meta.get("track") or track,
            "xesam:artist":  [meta.get("artist") or artist] if (meta.get("artist") or artist) else [],
            "xesam:album":   meta.get("album") or station_name,
        }
        if meta.get("genres"):
            mpris_meta["xesam:genre"] = meta["genres"]
        if meta.get("year"):
            mpris_meta["xesam:contentCreated"] = str(meta["year"])
        if meta.get("cover"):
            mpris_meta["mpris:artUrl"] = meta["cover"]

        self._metadata = mpris_meta
        self._emit_changed({"Metadata": dict_to_a_sv(self._metadata)})

    # --- Watcher thread ---

    def start_watcher(self, station: str = "Radio") -> None:
        """
        Start a background thread that polls MPV for ICY title changes
        and triggers metadata enrichment when the track changes.
        """
        def _run() -> None:
            while not self._stop.is_set():
                mpv_meta = mpv_get("metadata") or {}
                icy = mpv_meta.get("icy-title") or mpv_meta.get("title")
                if icy and icy != self._last_icy:
                    self._last_icy = icy
                    self._set_status("Playing")
                    self._update_metadata(station, icy)
                time.sleep(0.5)

        threading.Thread(target=_run, daemon=True, name="mpris-watcher").start()


SQLCHMPRIS.__doc__ = MPRIS_XML


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    station = os.environ.get("SQLCH_STATION_NAME", "Radio")
    bus     = SessionBus()
    mpris   = SQLCHMPRIS()
    bus.publish(BUS_NAME, (OBJ_PATH, mpris))
    mpris.start_watcher(station)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
