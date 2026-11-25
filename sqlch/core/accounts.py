"""Keys entered in the app, plus a live check for each service.

Stored in data_dir()/accounts.json (0600). An entry here beats the environment
and the secrets files; forgetting it falls back to them."""

import base64
import fcntl
import json
import time
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from sqlch.core.paths import cache_dir, data_dir, write_private

TIMEOUT = 8
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
FIELDS = {"spotify": ("client_id", "client_secret"),
          "jellyfin": ("server", "token"),
          "podcastindex": ("key", "secret")}


class CheckFailed(RuntimeError):
    pass


def _path():
    return data_dir() / "accounts.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@contextmanager
def _locked():
    with open(data_dir() / "accounts.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def get(service: str) -> tuple[str, ...] | None:
    """The stored values in FIELDS order, or None unless every one is set."""
    entry = _load().get(service)
    if not isinstance(entry, dict):
        return None
    vals = tuple(entry.get(f) for f in FIELDS[service])
    return vals if all(isinstance(v, str) and v for v in vals) else None


def save(service: str, values: dict) -> None:
    entry = {f: (values.get(f) or "").strip() for f in FIELDS[service]}
    if not all(entry.values()):
        raise ValueError("fill in every field")
    # a newline would let a pasted key inject extra request headers
    if any(not c.isprintable() for v in entry.values() for c in v):
        raise ValueError("a field contains unprintable characters")
    changed = get(service) != tuple(entry.values())
    with _locked():
        data = _load()
        data[service] = entry
        write_private(_path(), json.dumps(data))
    if service == "spotify" and changed:
        _drop_spotify_tokens()


def forget(service: str) -> None:
    with _locked():
        data = _load()
        if data.pop(service, None) is None:
            return
        write_private(_path(), json.dumps(data))
    if service == "spotify":
        _drop_spotify_tokens()


def _drop_spotify_tokens() -> None:
    """Tokens belong to the app id that made them."""
    from sqlch.core import spotify_auth
    (cache_dir() / "spotify_token.json").unlink(missing_ok=True)
    spotify_auth.clear()


# ---- live checks: raise CheckFailed with a sentence for the person ----

def _request(req: Request, who: str) -> bytes:
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except HTTPError as e:
        if e.code in (400, 401, 403):
            raise CheckFailed(f"{who} rejected these keys") from e
        raise CheckFailed(f"{who} answered with error {e.code}") from e
    except OSError as e:
        raise CheckFailed(f"Can't reach {who}") from e


def check(service: str, values: dict) -> None:
    v = {f: (values.get(f) or "").strip() for f in FIELDS[service]}
    if not all(v.values()):
        raise CheckFailed("Fill in every field")
    _CHECKS[service](v)


def _check_spotify(v: dict) -> None:
    from sqlch.sources import spotify
    basic = base64.b64encode(f"{v['client_id']}:{v['client_secret']}".encode()).decode()
    _request(Request(f"{spotify._auth_base()}/api/token",
                     data=urlencode({"grant_type": "client_credentials"}).encode(),
                     headers={"Authorization": f"Basic {basic}"}), "Spotify")


def _check_jellyfin(v: dict) -> None:
    u = urlparse(v["server"])
    if u.scheme not in ("http", "https") or not u.hostname:
        raise CheckFailed("The address must start with https://")
    if u.scheme == "http" and u.hostname not in LOOPBACK:
        raise CheckFailed("Use an https:// address, or the key is sent unencrypted")
    _request(Request(v["server"].rstrip("/") + "/Users",
                     headers={"Authorization": f'MediaBrowser Token="{v["token"]}"'}), "Jellyfin")


def _check_podcastindex(v: dict) -> None:
    from sqlch.sources import _podcast_dirs as dirs
    _request(Request(f"{dirs._pi_base()}/search/byterm?q=test&max=1", headers={
        "User-Agent": dirs.UA, **dirs.pi_headers(v["key"], v["secret"], time.time())}),
        "Podcast Index")


_CHECKS = {"spotify": _check_spotify, "jellyfin": _check_jellyfin,
           "podcastindex": _check_podcastindex}
