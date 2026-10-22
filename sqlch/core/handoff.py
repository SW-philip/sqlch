"""Playback delegated to an external player instead of mpv. Each handler takes
the Target url (a URI the player understands) and offers play, toggle, stop,
seek and progress. A new backend is another entry in HANDLERS."""

import json
import os
import re
import shutil
import subprocess
import time
from urllib.request import Request, urlopen

STARTUP_WAIT = 12.0


def _playerctl(*args: str, player: str) -> subprocess.CompletedProcess:
    exe = os.environ.get("SQLCH_PLAYERCTL") or shutil.which("playerctl")
    if exe is None:
        raise RuntimeError("playerctl not found")
    return subprocess.run([exe, "-p", player, *args], capture_output=True,
                          text=True, timeout=5)


_TRACK_ID = re.compile(r"track[:/]([A-Za-z0-9]+)")


def _track_uri(raw: str | None) -> str | None:
    m = _TRACK_ID.search(raw or "")
    return f"spotify:track:{m.group(1)}" if m else None


class Mpris:
    """An MPRIS player controlled with playerctl, launched on demand."""

    def __init__(self, player: str, launch: str):
        self.player, self.launch = player, launch

    def _running(self) -> bool:
        try:
            return self.player in _playerctl("-l", player=self.player).stdout.split() or \
                _playerctl("status", player=self.player).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _ensure_running(self) -> None:
        if self._running():
            return
        exe = shutil.which(self.launch)
        if exe is None:
            raise RuntimeError(f"{self.launch} is not installed")
        subprocess.Popen([exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + STARTUP_WAIT
        while time.monotonic() < deadline:
            if self._running():
                return
            time.sleep(0.5)
        raise RuntimeError(f"{self.launch} did not start")

    def play(self, uri: str) -> None:
        self._ensure_running()
        r = _playerctl("open", uri, player=self.player)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"{self.player} refused the uri")

    def toggle(self) -> None:
        _playerctl("play-pause", player=self.player)

    def stop(self) -> None:
        try:
            _playerctl("pause", player=self.player)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass

    def seek(self, pos: float) -> None:
        pass  # the external app owns its own position

    def progress(self) -> tuple[float | None, float | None]:
        return None, None

    def track_uri(self) -> str | None:
        r = _playerctl("metadata", "mpris:trackid", player=self.player)
        return _track_uri(r.stdout) if r.returncode == 0 else None

    def usable(self) -> bool:
        return True


class Librespot:
    """A go-librespot daemon driven through its local HTTP API."""

    def __init__(self, base: str | None = None):
        self._base = base

    @property
    def base(self) -> str:
        return (self._base or os.environ.get("SQLCH_LIBRESPOT_URL")
                or "http://localhost:3678").rstrip("/")

    def _call(self, path: str, body: dict | None = None, timeout: float = 3.0):
        data = json.dumps(body).encode() if body is not None else (
            b"" if path != "/" and path != "/status" else None)
        req = Request(self.base + path, data=data,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw and r.status == 200 else None

    def usable(self) -> bool:
        try:
            root = self._call("/", timeout=0.5)
        except (OSError, ValueError):
            return False
        return bool(root and root.get("playback_ready"))

    def play(self, uri: str) -> None:
        try:
            self._call("/player/play", {"uri": uri})
        except OSError as e:
            raise RuntimeError(f"go-librespot: {e}") from e

    def toggle(self) -> None:
        self._call("/player/playpause")

    def stop(self) -> None:
        try:
            self._call("/player/pause")
        except OSError:
            pass

    def seek(self, pos: float) -> None:
        self._call("/player/seek", {"position": int(pos * 1000)})

    def progress(self) -> tuple[float | None, float | None]:
        try:
            track = (self._call("/status") or {}).get("track") or {}
        except (OSError, ValueError):
            return None, None
        pos, dur = track.get("position"), track.get("duration")
        if pos is None or not dur:
            return None, None
        return pos / 1000, dur / 1000

    def track_uri(self) -> str | None:
        track = (self._call("/status") or {}).get("track") or {}
        return _track_uri(track.get("uri"))


class Preferred:
    """Use the primary handler while it is usable, else the fallback. The one
    chosen at play time keeps serving that track's controls."""

    def __init__(self, primary, fallback):
        self.primary, self.fallback, self.active = primary, fallback, fallback

    def play(self, uri: str) -> None:
        if self.primary.usable():
            try:
                self.primary.play(uri)
                self.active = self.primary
                return
            except RuntimeError:
                pass
        self.active = self.fallback
        self.fallback.play(uri)

    def toggle(self) -> None:
        self.active.toggle()

    def stop(self) -> None:
        self.active.stop()

    def seek(self, pos: float) -> None:
        self.active.seek(pos)

    def progress(self) -> tuple[float | None, float | None]:
        return self.active.progress()

    def track_uri(self) -> str | None:
        return self.active.track_uri()

    def usable(self) -> bool:
        return True


HANDLERS = {"spotify": Preferred(Librespot(), Mpris("spotify", "spotify"))}


def play(name: str, uri: str) -> None:
    HANDLERS[name].play(uri)


def toggle(name: str) -> None:
    HANDLERS[name].toggle()


def stop(name: str) -> None:
    handler = HANDLERS.get(name)
    if handler:
        handler.stop()


def seek(name: str, pos: float) -> None:
    HANDLERS[name].seek(pos)


def progress(name: str) -> tuple[float | None, float | None]:
    return HANDLERS[name].progress()


def track_uri(name: str) -> str | None:
    """The track the external player is on now, which differs from the one
    sqlch started once it autoplays or the user skips in the app."""
    try:
        return HANDLERS[name].track_uri()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return None
