"""Keeps the screen from dimming and locking while a video plays.

mpv blocks idle itself only while its window is visible. Audio doesn't count:
the screen may lock over it (hypridle's other steps check MPRIS instead)."""

import shutil
import subprocess

from sqlch.core import player

_held: subprocess.Popen | None = None


def wanted() -> bool:
    cur = player.current()
    if not cur or cur.get("type") != "item":
        return False
    if cur.get("handoff") or not player.mpv_get("vid"):
        return False
    # None (no mpv answering) must not count as playing
    return (player.mpv_get("pause") is False
            and player.mpv_get("eof-reached") is not True
            and player.mpv_get("idle-active") is not True)


def _hold() -> None:
    global _held
    if _held is not None and _held.poll() is None:
        return
    inhibit, cat = shutil.which("systemd-inhibit"), shutil.which("cat")
    if not (inhibit and cat):
        return
    # cat exits when our end of the pipe closes, so a dead daemon lets go too
    _held = subprocess.Popen(
        [inhibit, "--what=idle", "--mode=block", "--who=sqlch", "--why=Playing", cat],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def release() -> None:
    global _held
    proc, _held = _held, None
    if proc is None:
        return
    proc.stdin.close()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def update() -> None:
    if wanted():
        _hold()
    else:
        release()
