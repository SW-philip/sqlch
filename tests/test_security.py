import pytest

from sqlch.core import library, player
from sqlch.core.urlcheck import is_stream_url, require_stream_url
from sqlch.sources import jellyfin, podcasts


@pytest.mark.parametrize("url", [
    "--input-commands=run touch /tmp/x", "-i", "file:///etc/passwd",
    "edl://x", "av://lavfi:sine", "", None, "http://a b", "/etc/passwd",
])
def test_rejects_non_stream_urls(url):
    assert not is_stream_url(url)
    with pytest.raises(ValueError):
        require_stream_url(url)


@pytest.mark.parametrize("url", ["http://a.example/s", "https://a.example/s.mp3", "icy://a:80"])
def test_accepts_stream_urls(url):
    assert is_stream_url(url)


def test_mpv_url_follows_end_of_options():
    args = player._mpv_args("https://a.example/s")
    assert args[-2:] == ["--", "https://a.example/s"]
    assert "--ytdl=no" in args
    assert "--load-unsafe-playlists=no" in args


def test_add_station_refuses_option_url(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        library.add_station(name="x", url="--include=/tmp/evil.conf")


def test_play_station_refuses_option_url(monkeypatch):
    spawned = []
    monkeypatch.setattr(player, "_spawn_mpv", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(player, "stop", lambda **k: None)
    monkeypatch.setattr(player.notify, "notify", lambda *a: None)
    player.play_station({"id": "x", "name": "x", "url": "--script=/tmp/evil.lua"})
    assert not spawned


def test_preview_refuses_option_url():
    with pytest.raises(ValueError):
        player.preview("-f lavfi")


def test_runtime_dir_is_private(tmp_path, monkeypatch):
    from sqlch.core.paths import runtime_dir
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    d = runtime_dir()
    assert d.stat().st_mode & 0o777 == 0o700


def test_podcast_feed_with_dtd_refused():
    bomb = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><rss><channel/></rss>'
    with pytest.raises(ValueError, match="DTD"):
        podcasts.parse_feed(bomb, "https://a.example/f")


def test_jellyfin_refuses_plain_http(monkeypatch):
    monkeypatch.setattr(jellyfin, "_cfg", lambda: {"server": "http://box:8096"})
    with pytest.raises(ValueError, match="plain http"):
        jellyfin._server()
    monkeypatch.setattr(jellyfin, "_cfg", lambda: {"server": "http://box:8096", "allow_http": True})
    assert jellyfin._server() == "http://box:8096"
    monkeypatch.setattr(jellyfin, "_cfg", lambda: {"server": "http://localhost:8096"})
    assert jellyfin._server() == "http://localhost:8096"


def test_write_private_mode(tmp_path):
    from sqlch.core.paths import write_private
    p = tmp_path / "t.json"
    write_private(p, "{}")
    assert p.stat().st_mode & 0o777 == 0o600
