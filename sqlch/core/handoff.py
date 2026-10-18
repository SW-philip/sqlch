"""Playback delegated to an external app instead of mpv. Each handler takes
the Target url (a URI the app understands). A new backend, such as a
go-librespot service, is another entry in HANDLERS."""

import os
import shutil
import subprocess
import time

STARTUP_WAIT = 12.0


def _playerctl(*args: str, player: str) -> subprocess.CompletedProcess:
    exe = os.environ.get("SQLCH_PLAYERCTL") or shutil.which("playerctl")
    if exe is None:
        raise RuntimeError("playerctl not found")
    return subprocess.run([exe, "-p", player, *args], capture_output=True,
                          text=True, timeout=5)


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


HANDLERS = {"spotify": Mpris("spotify", "spotify")}


def play(name: str, uri: str) -> None:
    HANDLERS[name].play(uri)


def toggle(name: str) -> None:
    HANDLERS[name].toggle()


def stop(name: str) -> None:
    handler = HANDLERS.get(name)
    if handler:
        handler.stop()
