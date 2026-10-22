"""Validation for URLs that end up on a player's command line."""

import re

# What radio streams actually use; anything else (file:, edl:, av:, lavfi
# pseudo-protocols, option-looking strings) is refused.
_STREAM_URL = re.compile(r"^(https?|icy|icyx|mms|mmsh|mmst|rtmp|rtmps|rtsp)://[^\s]+$", re.I)


def is_stream_url(url) -> bool:
    return isinstance(url, str) and bool(_STREAM_URL.match(url.strip()))


def require_stream_url(url) -> str:
    if not is_stream_url(url):
        raise ValueError(f"not a valid stream url: {str(url)[:80]!r}")
    return url.strip()
