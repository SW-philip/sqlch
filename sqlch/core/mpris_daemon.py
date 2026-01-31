[prepko@SWsurface:~/src/sqlch]$ cat sqlch/core/mpris_daemon.py
#!/usr/bin/env python3
"""
SQLCH MPRIS daemon
- Listens to MPV ICY metadata via MPV IPC socket
- Enriches with Spotify (via sqlch.core.enrich)
- Publishes via MPRIS as org.mpris.MediaPlayer2.sqlch
"""

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pydbus import SessionBus
from pydbus.generic import signal
from gi.repository import GLib

from sqlch.core import enrich

MPV_SOCKET = Path("/tmp/sqlch-mpv.sock")
BUS_NAME = "org.mpris.MediaPlayer2.sqlch"
OBJ_PATH = "/org/mpris/MediaPlayer2"


# ------------------------------------------------------------
# GLib Variant helpers (CRITICAL)
# ------------------------------------------------------------

def V(sig: str, value):
    return GLib.Variant(sig, value)

def dict_to_a_sv(d: Dict[str, Any]) -> GLib.Variant:
    """
    Convert Python dict → a{sv} safely
    """
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, list):
            out[k] = V("as", v)
        elif isinstance(v, bool):
            out[k] = V("b", v)
        elif isinstance(v, int):
            out[k] = V("x", v)
        elif isinstance(v, float):
            out[k] = V("d", v)
        else:
            out[k] = V("s", str(v))
    return V("a{sv}", out)

def wrap_metadata(meta: Dict[str, Any]) -> GLib.Variant:
    """
    Convert Python MPRIS metadata dict into a{sv} with correct inner variants.
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


# ------------------------------------------------------------
# MPV IPC
# ------------------------------------------------------------

def _mpv_ipc(cmd: dict, timeout: float = 0.5) -> Optional[dict]:
    if not MPV_SOCKET.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(MPV_SOCKET))
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
    r = _mpv_ipc({"command": ["get_property", prop]})
    if r and r.get("error") == "success":
        return r.get("data")
    return None


def mpv_cmd(*args: str):
    _mpv_ipc({"command": list(args)})


# ------------------------------------------------------------
# ICY parsing
# ------------------------------------------------------------

def parse_icy_title(s: str) -> Tuple[Optional[str], Optional[str]]:
    if not s:
        return None, None
    if " - " in s:
        a, t = s.split(" - ", 1)
    elif "-" in s:
        a, t = s.split("-", 1)
    else:
        return None, s.strip()
    return a.strip() or None, t.strip() or None

# ------------------------------------------------------------
# MPRIS XML
# ------------------------------------------------------------

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
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
    <method name="Raise"/>
    <method name="Quit"/>
  </interface>

  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Play"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>

    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""

# ------------------------------------------------------------
# MPRIS implementation
# ------------------------------------------------------------

class SQLCHMPRIS:
    PropertiesChanged = signal()

    def __init__(self):
        self._playback_status = "Stopped"
        self._metadata: Dict[str, Any] = {}
        self._volume = 1.0
        self._last_icy: Optional[str] = None
        self._stop = threading.Event()

    # ---- DBus Properties ----

    def Get(self, interface: str, prop: str):
        # If the property exists, return it
        if hasattr(self, prop):
            val = getattr(self, prop)

            if interface == "org.mpris.MediaPlayer2.Player" and prop == "Metadata":
                return dict_to_a_sv(val)

            if isinstance(val, bool):
                return V("b", val)
            if isinstance(val, int):
                return V("x", val)
            if isinstance(val, float):
                return V("d", val)
            if isinstance(val, list):
                return V("as", val)

            return V("s", str(val))

        # Otherwise: return a harmless default instead of throwing
        # This keeps playerctl and other clients happy
        return V("s", "")




    def Set(self, iface, prop, value):
        if iface == "org.mpris.MediaPlayer2.Player" and prop == "Volume":
            self.Volume = float(value)
            return
        raise Exception("org.freedesktop.DBus.Error.PropertyReadOnly")

    def GetAll(self, interface: str):
        props = {}
        for attr in dir(self):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(self, attr)
            except Exception:
                continue
            if interface.endswith("Player") and attr == "Metadata":
                props[attr] = dict_to_a_sv(val)
            elif isinstance(val, bool):
               props[attr] = V("b", val)
            elif isinstance(val, int):
                props[attr] = V("x", val)
            elif isinstance(val, float):
                props[attr] = V("d", val)
            elif isinstance(val, str):
                props[attr] = V("s", val)
        return props


    def _emit_player_changed(self, changed: Dict[str, GLib.Variant]):
        def _emit():
            self.PropertiesChanged(
                "org.mpris.MediaPlayer2.Player",
                changed,
                []
            )
            return False
        GLib.idle_add(_emit)


    # ---- Player properties ----

    @property
    def PlaybackStatus(self):
        return self._playback_status

    @property
    def Metadata(self):
        return self._metadata

    @property
    def Volume(self):
        return self._volume

    @Volume.setter
    def Volume(self, v: float):
        self._volume = max(0.0, float(v))
        mpv_cmd("set_property", "volume", str(self._volume * 100))
        self._emit_player_changed({
            "Volume": V("d", self._volume)
        })


    @property
    def Position(self):
        t = mpv_get("playback-time")
        return int(float(t) * 1_000_000) if t else 0

    # ---- Controls ----

    def Play(self):
        mpv_cmd("set_property", "pause", "no")
        self._set_status("Playing")

    def Pause(self):
        mpv_cmd("set_property", "pause", "yes")
        self._set_status("Paused")

    def Stop(self):
        mpv_cmd("quit")
        self._set_status("Stopped")

    def PlayPause(self):
        mpv_cmd("cycle", "pause")

    def _set_status(self, status: str):
        if status != self._playback_status:
            self._playback_status = status
            self._emit_player_changed({
                "PlaybackStatus": V("s", self._playback_status)
            })

    # ---- Enrichment ----

    def set_enriched_metadata(self, station_name: str, icy_title: str):
        artist, track = parse_icy_title(icy_title)
        if not track:
            return

        meta = enrich.enrich_track(artist or "", track)

        self._last_trackid = "/org/mpris/MediaPlayer2/Track/0"

        mpris_meta: Dict[str, Any] = {
            "mpris:trackid": self._last_trackid,
            "xesam:title": meta.get("track") or track,
            "xesam:artist": [meta.get("artist") or artist] if (meta.get("artist") or artist) else [],
            "xesam:album": meta.get("album") or station_name,
        }

        if meta.get("genres"):
            mpris_meta["xesam:genre"] = meta["genres"]

        if meta.get("year"):
            mpris_meta["xesam:contentCreated"] = str(meta["year"])

        if meta.get("cover"):
            mpris_meta["mpris:artUrl"] = meta["cover"]

        self._metadata = mpris_meta

        self._emit_player_changed({
            "Metadata": dict_to_a_sv(self._metadata)
        })


    # ---- Watcher ----

    def start_watcher(self, station="Radio"):
        def _run():
            while not self._stop.is_set():
                meta = mpv_get("metadata") or {}
                icy = meta.get("icy-title") or meta.get("title")
                if icy and icy != self._last_icy:
                    self._last_icy = icy
                    self.set_enriched_metadata(station, icy)
                time.sleep(0.5)
        threading.Thread(target=_run, daemon=True).start()

SQLCHMPRIS.__doc__ = MPRIS_XML

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    station = os.environ.get("SQLCH_STATION_NAME", "Radio")
    bus = SessionBus()
    mpris = SQLCHMPRIS()
    bus.publish(BUS_NAME, (OBJ_PATH, mpris))
    mpris.start_watcher(station)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
