"""Lightweight ICY StreamTitle prober: one short request per station, no playback.

Speaks raw HTTP because Shoutcast v1 servers answer with a bare "ICY 200 OK"
status line that http.client rejects.
"""

import re
import socket
import ssl
import time
from urllib.parse import urlparse, urljoin

_MAX_METAINT = 64 * 1024
_MAX_HEADER = 32 * 1024
_MAX_HOPS = 3
_MAX_PROBE_BYTES = 4 * 1024 * 1024
_BASE_BUDGET = 4.0
_AD_GRACE = 8.0
_MAX_AD_WAIT = 45.0

_TITLE_RE = re.compile(r"StreamTitle='(.*?)';")
_AD_DURATION_RE = re.compile(r"durationMilliseconds='(\d+)'")
# iHeart in-band markers: song_spot M is music; T/A are promos/ads with a length
_SPOT_RE = re.compile(r'song_spot="(\w)"')
_SPOT_LEN_RE = re.compile(r'length="(\d+):(\d+):(\d+)"')


def _normalize(url: str) -> str:
    """iHeart HLS playlists carry no ICY; their direct AAC mount does."""
    u = urlparse(url)
    if u.hostname and u.hostname.endswith("ihrhls.com") and u.path.endswith("/hls.m3u8"):
        return url[: -len("/hls.m3u8")]
    return url


def _recv_until(sock, buf: bytes, target_len: int) -> bytes | None:
    while len(buf) < target_len:
        chunk = sock.recv(8192)
        if not chunk:
            return None
        buf += chunk
    return buf


def fetch_stream_title(url: str, timeout: float = 4.0, _hops: int = 0) -> str | None:
    """Return the current StreamTitle of an ICY stream, or None."""
    if _hops > _MAX_HOPS:
        return None
    try:
        url = _normalize(url)
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return None
        port = u.port or (443 if u.scheme == "https" else 80)
        path = u.path or "/"
        if u.query:
            path += "?" + u.query

        sock = socket.create_connection((u.hostname, port), timeout=timeout)
        try:
            if u.scheme == "https":
                ctx = ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=u.hostname)
            sock.sendall(
                (
                    f"GET {path} HTTP/1.0\r\n"
                    f"Host: {u.hostname}\r\n"
                    "Icy-MetaData: 1\r\n"
                    "User-Agent: sqlch-gui\r\n"
                    "Accept: */*\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
            )

            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(2048)
                if not chunk or len(buf) > _MAX_HEADER:
                    return None
                buf += chunk
            head, body = buf.split(b"\r\n\r\n", 1)

            lines = head.decode("latin-1", "replace").split("\r\n")
            parts = lines[0].split()
            code = parts[1] if len(parts) > 1 else ""
            headers = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            if code in ("301", "302", "303", "307", "308"):
                loc = headers.get("location")
                if not loc:
                    return None
                return fetch_stream_title(urljoin(url, loc), timeout, _hops + 1)
            if code != "200":
                return None

            metaint = int(headers.get("icy-metaint", "0") or 0)
            if not 0 < metaint <= _MAX_METAINT:
                return None

            # Read successive metadata blocks until a real track title shows.
            # Ad-insertion servers (AIS, iHeart, STW) open every connection
            # with pre-roll ads/promos; their metadata announces the spot's
            # duration, so extend the deadline past it and keep discarding
            # stream bytes until the live title cuts in.
            start = time.monotonic()
            deadline = start + _BASE_BUDGET
            hard_stop = start + _MAX_AD_WAIT
            consumed = 0
            while time.monotonic() < deadline and consumed < _MAX_PROBE_BYTES:
                body = _recv_until(sock, body, metaint + 1)
                if body is None:
                    return None
                meta_len = body[metaint] * 16
                if meta_len:
                    body = _recv_until(sock, body, metaint + 1 + meta_len)
                    if body is None:
                        return None
                    meta = body[metaint + 1 : metaint + 1 + meta_len].decode(
                        "utf-8", "replace"
                    )
                    m = _TITLE_RE.search(meta)
                    title = m.group(1).strip() if m else ""
                    spot = _SPOT_RE.search(title)
                    if title and (spot is None or spot.group(1).upper() == "M"):
                        return title
                    wait = None
                    if spot:  # iHeart promo/ad spot with an hh:mm:ss length
                        ln = _SPOT_LEN_RE.search(title)
                        wait = (
                            int(ln.group(1)) * 3600
                            + int(ln.group(2)) * 60
                            + int(ln.group(3))
                            if ln
                            else 20.0
                        )
                    else:
                        ad = _AD_DURATION_RE.search(meta)
                        if ad:
                            wait = int(ad.group(1)) / 1000.0
                    if wait is not None:
                        deadline = min(
                            time.monotonic() + wait + _AD_GRACE, hard_stop
                        )
                consumed += metaint + 1 + meta_len
                body = body[metaint + 1 + meta_len :]
            return None
        finally:
            sock.close()
    except Exception:
        return None
