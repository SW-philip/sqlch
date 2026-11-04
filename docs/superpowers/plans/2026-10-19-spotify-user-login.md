# Spotify User Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Spotify pane list the logged-in user's playlists (including private) and followed artists, via a `sqlch spotify-login` OAuth PKCE login.

**Architecture:** A new `sqlch/core/spotify_auth.py` owns the PKCE login, token file and refresh. `sqlch/sources/spotify.py` uses the user token when logged in (app token otherwise) and gains PLAYLISTS and ARTISTS sections. Two CLI commands drive login and logout.

**Tech Stack:** Python 3.11 stdlib only (`http.server`, `urllib`, `hashlib`), `unittest`.

## Global Constraints

- Work and push on branch `unstable` (tracks `origin/unstable`). NEVER push to `main` or `stable`.
- Tests are `unittest`: `python3 -m unittest tests.test_x -v`; whole suite `python3 -m unittest discover -s tests -t .`. Three errors in `tests.test_header.TestPreviousTracksReserveSpace` are pre-existing and unrelated.
- Stdlib only (the GUI process has no `requests`).
- Scopes are exactly `playlist-read-private playlist-read-collaborative user-follow-read`.
- Token file: `data_dir()/spotify_user.json`, mode 0600, atomic write. Redirect URI `http://127.0.0.1:<port>/callback`, default port 8888, config `sources.spotify.redirect_port`.
- Endpoint base honours `SQLCH_SPOTIFY_AUTH_BASE` (existing override).
- Paging: 50 per page, at most 200 items.
- Commit trailer on every commit: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Spec: `docs/superpowers/specs/2026-10-19-spotify-user-login-design.md`.

## File Structure

- Create `sqlch/core/spotify_auth.py`; test `tests/test_spotify_auth.py`.
- Modify `sqlch/sources/spotify.py`; extend `tests/test_source_spotify.py`.
- Modify `sqlch/cli/main.py`; create `tests/test_cli_spotify.py`.

---

### Task 1: Login module

**Files:**
- Create: `sqlch/core/spotify_auth.py`
- Test: `tests/test_spotify_auth.py`

**Interfaces:**
- Produces (in `sqlch.core.spotify_auth`):
  - `class AuthError(RuntimeError)`, `class NotLoggedIn(AuthError)`
  - `SCOPES: str`, `DEFAULT_PORT = 8888`, `LOGIN_HINT = "run `sqlch spotify-login`"`
  - `new_verifier() -> str`, `challenge(verifier: str) -> str`, `redirect_uri(port: int) -> str`, `authorize_url(client_id, port, verifier, state) -> str`
  - `logged_in() -> bool`, `clear() -> None`
  - `access_token(client_id: str) -> str` (raises `NotLoggedIn`/`AuthError`)
  - `login(client_id: str, port: int = DEFAULT_PORT, open_browser=webbrowser.open, wait: float = 180, say=print) -> None` (raises `AuthError`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_spotify_auth.py`:

```python
import io
import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from sqlch.core import spotify_auth as auth


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        p = mock.patch.object(auth, "data_dir", lambda: self.dir)
        p.start()
        self.addCleanup(p.stop)

    def token_file(self, **kw):
        tok = {"access_token": "OLD", "refresh_token": "R1", "expires_at": 0, **kw}
        (self.dir / "spotify_user.json").write_text(json.dumps(tok))


class TestPkce(unittest.TestCase):
    def test_challenge_matches_rfc7636_vector(self):
        self.assertEqual(
            auth.challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_verifier_is_url_safe_and_in_range(self):
        v = auth.new_verifier()
        self.assertTrue(43 <= len(v) <= 128)
        self.assertRegex(v, r"^[A-Za-z0-9_-]+$")
        self.assertNotEqual(v, auth.new_verifier())

    def test_authorize_url(self):
        url = auth.authorize_url("CID", 8888, "ver", "ST")
        q = parse_qs(urlparse(url).query)
        self.assertEqual(urlparse(url).path, "/authorize")
        self.assertEqual(q["client_id"], ["CID"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:8888/callback"])
        self.assertEqual(q["scope"], [auth.SCOPES])
        self.assertEqual(q["state"], ["ST"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["code_challenge"], [auth.challenge("ver")])

    def test_scopes_are_exactly_the_read_scopes(self):
        self.assertEqual(auth.SCOPES.split(),
                         ["playlist-read-private", "playlist-read-collaborative",
                          "user-follow-read"])

    def test_auth_base_override(self):
        with mock.patch.dict(os.environ, {"SQLCH_SPOTIFY_AUTH_BASE": "http://fake"}):
            self.assertTrue(auth.authorize_url("c", 1, "v", "s").startswith("http://fake/authorize?"))


class TestStore(Base):
    def test_not_logged_in_without_file(self):
        self.assertFalse(auth.logged_in())

    def test_corrupt_or_tokenless_file_is_logged_out(self):
        (self.dir / "spotify_user.json").write_text("{nope")
        self.assertFalse(auth.logged_in())
        (self.dir / "spotify_user.json").write_text('{"access_token": "x"}')
        self.assertFalse(auth.logged_in())

    def test_save_is_0600_and_round_trips(self):
        auth._save({"access_token": "A", "refresh_token": "R", "expires_at": 1})
        path = self.dir / "spotify_user.json"
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertTrue(auth.logged_in())
        self.assertEqual([p.name for p in self.dir.iterdir()], ["spotify_user.json"])

    def test_clear(self):
        self.token_file()
        auth.clear()
        self.assertFalse(auth.logged_in())
        auth.clear()  # no error when already gone


def _http_error(code, body):
    return HTTPError("http://x", code, "err", {}, io.BytesIO(body))


class TestAccessToken(Base):
    def test_missing_file_raises_not_logged_in(self):
        with self.assertRaisesRegex(auth.NotLoggedIn, "spotify-login"):
            auth.access_token("CID")

    def test_valid_token_is_reused_without_network(self):
        self.token_file(access_token="GOOD", expires_at=9e12)
        with mock.patch.object(auth, "_post_token") as post:
            self.assertEqual(auth.access_token("CID"), "GOOD")
        post.assert_not_called()

    def test_expired_token_is_refreshed_and_saved(self):
        self.token_file()
        resp = {"access_token": "NEW", "refresh_token": "R2", "expires_in": 3600}
        with mock.patch.object(auth, "_post_token", return_value=resp) as post, \
             mock.patch.object(auth.time, "time", return_value=1000.0):
            self.assertEqual(auth.access_token("CID"), "NEW")
        post.assert_called_once_with({"grant_type": "refresh_token",
                                      "refresh_token": "R1", "client_id": "CID"})
        saved = json.loads((self.dir / "spotify_user.json").read_text())
        self.assertEqual((saved["access_token"], saved["refresh_token"], saved["expires_at"]),
                         ("NEW", "R2", 4600.0))

    def test_refresh_without_new_refresh_token_keeps_the_old_one(self):
        self.token_file()
        with mock.patch.object(auth, "_post_token",
                               return_value={"access_token": "NEW", "expires_in": 60}):
            auth.access_token("CID")
        saved = json.loads((self.dir / "spotify_user.json").read_text())
        self.assertEqual(saved["refresh_token"], "R1")

    def test_token_expiring_within_the_margin_is_refreshed(self):
        self.token_file(access_token="SOON", expires_at=1010.0)
        with mock.patch.object(auth, "_post_token",
                               return_value={"access_token": "NEW", "expires_in": 60}), \
             mock.patch.object(auth.time, "time", return_value=1000.0):
            self.assertEqual(auth.access_token("CID"), "NEW")

    def test_invalid_grant_clears_the_file_and_asks_to_log_in_again(self):
        self.token_file()
        with mock.patch.object(auth, "urlopen",
                               side_effect=_http_error(400, b'{"error": "invalid_grant"}')):
            with self.assertRaisesRegex(auth.NotLoggedIn, "expired"):
                auth.access_token("CID")
        self.assertFalse(auth.logged_in())

    def test_other_refresh_errors_keep_the_file(self):
        self.token_file()
        with mock.patch.object(auth, "urlopen",
                               side_effect=_http_error(503, b"upstream down")):
            with self.assertRaisesRegex(auth.AuthError, "503"):
                auth.access_token("CID")
        self.assertTrue(auth.logged_in())


class TestLogin(Base):
    def _browser(self, **query):
        """open_browser stand-in: calls the redirect URI like Spotify would."""
        seen = {}

        def open_browser(url):
            q = parse_qs(urlparse(url).query)
            seen["url"] = url
            port = urlparse(q["redirect_uri"][0]).port
            params = {"state": q["state"][0], "code": "CODE", **query}
            params = {k: v for k, v in params.items() if v is not None}
            qs = "&".join(f"{k}={v}" for k, v in params.items())

            def hit():
                try:
                    urlopen(f"http://127.0.0.1:{port}/callback?{qs}", timeout=5).read()
                except Exception:
                    pass

            threading.Thread(target=hit, daemon=True).start()

        return open_browser, seen

    def test_login_exchanges_the_code_and_saves_tokens(self):
        browser, seen = self._browser()
        resp = {"access_token": "A", "refresh_token": "R", "expires_in": 3600}
        with mock.patch.object(auth, "_post_token", return_value=resp) as post:
            auth.login("CID", port=0, open_browser=browser, wait=10, say=lambda s: None)
        (data,), _ = post.call_args
        q = parse_qs(urlparse(seen["url"]).query)
        self.assertEqual(data["grant_type"], "authorization_code")
        self.assertEqual(data["code"], "CODE")
        self.assertEqual(data["client_id"], "CID")
        self.assertEqual(data["redirect_uri"], q["redirect_uri"][0])
        self.assertEqual(auth.challenge(data["code_verifier"]), q["code_challenge"][0])
        self.assertTrue(auth.logged_in())

    def test_state_mismatch_fails_and_saves_nothing(self):
        browser, _ = self._browser(state="WRONG")
        with mock.patch.object(auth, "_post_token") as post:
            with self.assertRaisesRegex(auth.AuthError, "state"):
                auth.login("CID", port=0, open_browser=browser, wait=10, say=lambda s: None)
        post.assert_not_called()
        self.assertFalse(auth.logged_in())

    def test_denied_login_fails_with_the_error_code(self):
        browser, _ = self._browser(error="access_denied", code=None)
        with mock.patch.object(auth, "_post_token") as post:
            with self.assertRaisesRegex(auth.AuthError, "access_denied"):
                auth.login("CID", port=0, open_browser=browser, wait=10, say=lambda s: None)
        post.assert_not_called()

    def test_no_callback_times_out(self):
        with mock.patch.object(auth, "_post_token") as post:
            with self.assertRaisesRegex(auth.AuthError, "timed out"):
                auth.login("CID", port=0, open_browser=lambda url: None, wait=0.2,
                           say=lambda s: None)
        post.assert_not_called()

    def test_port_in_use_is_a_clear_error(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        self.addCleanup(s.close)
        with self.assertRaisesRegex(auth.AuthError, "listen"):
            auth.login("CID", port=s.getsockname()[1], open_browser=lambda u: None,
                       wait=0.2, say=lambda x: None)

    def test_say_gets_the_authorize_url(self):
        lines = []
        with self.assertRaises(auth.AuthError):
            auth.login("CID", port=0, open_browser=lambda url: None, wait=0.2, say=lines.append)
        self.assertIn("/authorize?", lines[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_spotify_auth -v`
Expected: ERROR `ImportError: cannot import name 'spotify_auth'`.

- [ ] **Step 3: Write the implementation**

Create `sqlch/core/spotify_auth.py`:

```python
"""Spotify user login (authorization code + PKCE) for the Web API.

No client secret is involved. Tokens live in data_dir()/spotify_user.json
(mode 0600); writes are atomic renames so the gui and daemon can both read."""

import base64
import hashlib
import json
import os
import secrets
import tempfile
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from sqlch.core.paths import data_dir

SCOPES = "playlist-read-private playlist-read-collaborative user-follow-read"
DEFAULT_PORT = 8888
LOGIN_WAIT = 180
TIMEOUT = 8
EXPIRY_MARGIN = 30  # refresh when the token has less than this many seconds left
LOGIN_HINT = "run `sqlch spotify-login`"


class AuthError(RuntimeError):
    pass


class NotLoggedIn(AuthError):
    pass


def _auth_base() -> str:
    return os.environ.get("SQLCH_SPOTIFY_AUTH_BASE", "https://accounts.spotify.com")


def new_verifier() -> str:
    return secrets.token_urlsafe(64)


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/callback"


def authorize_url(client_id: str, port: int, verifier: str, state: str) -> str:
    query = urlencode({
        "client_id": client_id, "response_type": "code",
        "redirect_uri": redirect_uri(port), "scope": SCOPES, "state": state,
        "code_challenge_method": "S256", "code_challenge": challenge(verifier)})
    return f"{_auth_base()}/authorize?{query}"


# ---- token file ----

def _path():
    return data_dir() / "spotify_user.json"


def _load() -> dict | None:
    try:
        tok = json.loads(_path().read_text())
    except (OSError, ValueError):
        return None
    return tok if isinstance(tok, dict) and tok.get("refresh_token") else None


def _save(tok: dict) -> None:
    path = _path()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="spotify_user.")
    try:
        with os.fdopen(fd, "w") as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(tok, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def logged_in() -> bool:
    return _load() is not None


def clear() -> None:
    try:
        _path().unlink()
    except FileNotFoundError:
        pass


# ---- token endpoint ----

def _post_token(data: dict) -> dict:
    req = Request(f"{_auth_base()}/api/token", data=urlencode(data).encode(),
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except HTTPError as e:
        try:
            err = json.loads(e.read()).get("error")
        except (ValueError, AttributeError, OSError):
            err = None
        raise AuthError(err or f"HTTP {e.code}") from e
    except OSError as e:
        raise AuthError(f"can't reach Spotify: {e}") from e


def _store_token(resp: dict, old: dict | None = None) -> dict:
    tok = {"access_token": resp["access_token"],
           "refresh_token": resp.get("refresh_token") or (old or {}).get("refresh_token"),
           "expires_at": time.time() + resp.get("expires_in", 3600)}
    if not tok["refresh_token"]:
        raise AuthError("Spotify returned no refresh token")
    _save(tok)
    return tok


def access_token(client_id: str) -> str:
    tok = _load()
    if tok is None:
        raise NotLoggedIn(f"Not logged in to Spotify: {LOGIN_HINT}")
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time() + EXPIRY_MARGIN:
        return tok["access_token"]
    try:
        resp = _post_token({"grant_type": "refresh_token",
                            "refresh_token": tok["refresh_token"], "client_id": client_id})
    except AuthError as e:
        if str(e) == "invalid_grant":
            clear()
            raise NotLoggedIn(f"Spotify login expired: {LOGIN_HINT}") from e
        raise
    return _store_token(resp, tok)["access_token"]


# ---- interactive login ----

class _Callback(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/callback":
            self.send_error(404)
            return
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.server.result = query
        body = (b"sqlch: you can close this tab." if "code" in query
                else b"sqlch: login failed, see the terminal.")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def login(client_id: str, port: int = DEFAULT_PORT, open_browser=webbrowser.open,
          wait: float = LOGIN_WAIT, say=print) -> None:
    try:
        server = HTTPServer(("127.0.0.1", port), _Callback)
    except OSError as e:
        raise AuthError(f"can't listen on 127.0.0.1:{port}: {e}") from e
    server.result = None
    server.timeout = 1
    actual = server.server_address[1]
    verifier, state = new_verifier(), secrets.token_urlsafe(16)
    url = authorize_url(client_id, actual, verifier, state)
    try:
        say(f"Opening your browser to log in to Spotify.\nIf it does not open, visit:\n{url}")
        open_browser(url)
        deadline = time.monotonic() + wait
        while server.result is None and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    result = server.result
    if result is None:
        raise AuthError("login timed out")
    if result.get("error"):
        raise AuthError(f"Spotify refused the login: {result['error']}")
    if result.get("state") != state:
        raise AuthError("login state mismatch")
    code = result.get("code")
    if not code:
        raise AuthError("no authorization code received")
    resp = _post_token({"grant_type": "authorization_code", "code": code,
                        "redirect_uri": redirect_uri(actual), "client_id": client_id,
                        "code_verifier": verifier})
    _store_token(resp)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_spotify_auth -v`
Expected: all PASS, no hangs (the login tests use port 0 and a 0.2-10 s wait).

- [ ] **Step 5: Commit**

```bash
git add sqlch/core/spotify_auth.py tests/test_spotify_auth.py
git commit -m "sqlch: spotify user login (PKCE) module with token store and refresh

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin unstable
```

---

### Task 2: Spotify source uses the user token and gains library sections

**Files:**
- Modify: `sqlch/sources/spotify.py`
- Test: `tests/test_source_spotify.py`

**Interfaces:**
- Consumes: `spotify_auth.logged_in()`, `spotify_auth.access_token(client_id)`, `spotify_auth.DEFAULT_PORT` (Task 1).
- Produces:
  - `spotify.client_id() -> str | None`
  - `spotify.redirect_port() -> int`
  - `spotify.sections()` -> `[shortcuts, playlists, artists]`
  - `spotify.browse("section:playlists")` and `browse("section:artists")` (raise `RuntimeError` containing "spotify-login" when logged out)

- [ ] **Step 1: Write the failing tests**

In `tests/test_source_spotify.py`, change the existing `test_sections` (added earlier) so it expects the new list:

```python
    def test_sections(self):
        self.assertEqual([s["id"] for s in spotify.sections()],
                         ["shortcuts", "playlists", "artists"])
```

Append these tests inside `class TestSpotify` (before `if __name__`):

```python
    def logged_in(self, value=True):
        p = mock.patch.object(spotify.spotify_auth, "logged_in", return_value=value)
        p.start()
        self.addCleanup(p.stop)

    def test_client_id_and_redirect_port(self):
        self.assertEqual(spotify.client_id(), "abc")
        self.assertEqual(spotify.redirect_port(), 8888)
        self.cfg(env_file=str(self.env), redirect_port=9001)
        self.assertEqual(spotify.redirect_port(), 9001)
        self.cfg(env_file=str(self.env), redirect_port="nope")
        self.assertEqual(spotify.redirect_port(), 8888)
        self.cfg(env_file=str(self.dir / "missing"))
        self.assertIsNone(spotify.client_id())

    def test_get_uses_the_user_token_when_logged_in(self):
        self.logged_in()
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b'{"ok": 1}'
        with mock.patch.object(spotify.spotify_auth, "access_token",
                               return_value="USER") as at, \
             mock.patch.object(spotify, "urlopen", return_value=resp) as op:
            self.assertEqual(spotify._get("/x"), {"ok": 1})
        self.assertEqual(op.call_args[0][0].get_header("Authorization"), "Bearer USER")
        at.assert_called_once_with("abc")

    def test_get_uses_the_app_token_when_logged_out(self):
        self.logged_in(False)
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = b'{"ok": 1}'
        with mock.patch.object(spotify, "_token", return_value="APP"), \
             mock.patch.object(spotify, "urlopen", return_value=resp) as op:
            spotify._get("/x")
        self.assertEqual(op.call_args[0][0].get_header("Authorization"), "Bearer APP")

    def test_library_sections_need_login(self):
        self.logged_in(False)
        for sec in ("section:playlists", "section:artists"):
            with self.assertRaisesRegex(RuntimeError, "spotify-login"):
                spotify.browse(sec)

    def test_playlists_section_maps_items(self):
        self.logged_in()
        page = {"items": [{"id": "P1", "name": "Mine"}, None, {"name": "no id"}],
                "next": None}
        with mock.patch.object(spotify, "_get", return_value=page) as get:
            out = spotify.browse("section:playlists")
        self.assertEqual([(i["title"], i["kind"], i["path"]) for i in out],
                         [("Mine", "folder", "playlist:P1")])
        get.assert_called_once_with("/me/playlists", {"limit": 50, "offset": 0})

    def test_playlists_page_by_offset_until_next_is_empty(self):
        self.logged_in()
        pages = [{"items": [{"id": f"A{i}", "name": "a"} for i in range(50)], "next": "u"},
                 {"items": [{"id": "B", "name": "b"}], "next": None}]
        with mock.patch.object(spotify, "_get", side_effect=pages) as get:
            out = spotify.browse("section:playlists")
        self.assertEqual(len(out), 51)
        self.assertEqual([c.args[1]["offset"] for c in get.call_args_list], [0, 50])

    def test_playlists_are_capped_at_200(self):
        self.logged_in()
        page = lambda n: {"items": [{"id": f"P{n}-{i}", "name": "p"} for i in range(50)],
                          "next": "more"}
        with mock.patch.object(spotify, "_get", side_effect=[page(n) for n in range(10)]) as get:
            out = spotify.browse("section:playlists")
        self.assertEqual(len(out), 200)
        self.assertEqual(get.call_count, 4)

    def test_artists_section_pages_by_cursor(self):
        self.logged_in()
        pages = [{"artists": {"items": [{"id": "AR1", "name": "One"}],
                              "cursors": {"after": "AR1"}}},
                 {"artists": {"items": [{"id": "AR2", "name": "Two"}, None],
                              "cursors": {"after": None}}}]
        with mock.patch.object(spotify, "_get", side_effect=pages) as get:
            out = spotify.browse("section:artists")
        self.assertEqual([(i["title"], i["path"]) for i in out],
                         [("One", "artist:AR1"), ("Two", "artist:AR2")])
        self.assertEqual(get.call_args_list[0].args,
                         ("/me/following", {"type": "artist", "limit": 50}))
        self.assertEqual(get.call_args_list[1].args,
                         ("/me/following", {"type": "artist", "limit": 50, "after": "AR1"}))

    def test_artists_are_capped_at_200(self):
        self.logged_in()
        n = iter(range(100))

        def page(*a, **k):
            return {"artists": {"items": [{"id": f"X{next(n)}", "name": "x"}
                                          for _ in range(50)],
                                "cursors": {"after": "more"}}}

        with mock.patch.object(spotify, "_get", side_effect=page) as get:
            out = spotify.browse("section:artists")
        self.assertEqual(len(out), 200)
        self.assertEqual(get.call_count, 4)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_source_spotify -v`
Expected: FAIL/ERROR (`spotify_auth` attribute, `client_id`, new sections missing).

- [ ] **Step 3: Implement**

In `sqlch/sources/spotify.py`:

Add the import after `from sqlch.core.paths import cache_dir`:

```python
from sqlch.core import spotify_auth
```

Add constants after `LIST_LIMIT = 50`:

```python
MAX_ITEMS = 200
PAGE = 50
LOGIN_NEEDED = f"Not logged in to Spotify: {spotify_auth.LOGIN_HINT}"
```

Add after `available()`:

```python
def client_id() -> str | None:
    creds = _credentials()
    return creds[0] if creds else None


def redirect_port() -> int:
    cfg = source_config(NAME)
    port = cfg.get("redirect_port") if isinstance(cfg, dict) else None
    return port if isinstance(port, int) and not isinstance(port, bool) else spotify_auth.DEFAULT_PORT
```

Replace `_get` with a bearer-aware version:

```python
def _bearer() -> str:
    """The user's token when logged in (reads private playlists), else the app token."""
    if spotify_auth.logged_in():
        cid = client_id()
        if cid is None:
            raise RuntimeError("spotify credentials missing")
        return spotify_auth.access_token(cid)
    return _token()


def _get(path: str, params: dict | None = None) -> dict:
    url = _api() + path + (f"?{urlencode(params)}" if params else "")
    req = Request(url, headers={"Authorization": f"Bearer {_bearer()}"})
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())
```

Replace `sections` and add the library helpers right before `browse`:

```python
def sections() -> list[dict]:
    return [{"id": "shortcuts", "title": "SHORTCUTS"},
            {"id": "playlists", "title": "PLAYLISTS"},
            {"id": "artists", "title": "ARTISTS"}]


def _need_login() -> None:
    if not spotify_auth.logged_in():
        raise RuntimeError(LOGIN_NEEDED)


def _my_playlists() -> list[dict]:
    out, offset = [], 0
    while len(out) < MAX_ITEMS:
        data = _get("/me/playlists", {"limit": PAGE, "offset": offset})
        items = data.get("items") or []
        out += items
        if not data.get("next") or not items:
            break
        offset += PAGE
    return out[:MAX_ITEMS]


def _followed_artists() -> list[dict]:
    out, after = [], None
    while len(out) < MAX_ITEMS:
        params = {"type": "artist", "limit": PAGE}
        if after:
            params["after"] = after
        data = _get("/me/following", params).get("artists") or {}
        items = data.get("items") or []
        out += items
        after = (data.get("cursors") or {}).get("after")
        if not after or not items:
            break
    return out[:MAX_ITEMS]
```

In `browse`, add two branches right after the shortcuts branch (before `kind, _, sid = path.partition(":")`):

```python
    if path == "section:playlists":
        _need_login()
        return _compact(_folder("playlist", p) for p in _my_playlists())
    if path == "section:artists":
        _need_login()
        return _compact(_folder("artist", a) for a in _followed_artists())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_source_spotify tests.test_sources -v`
Expected: all PASS (including the pre-existing spotify tests and `test_registered_sources_have_sections`).

- [ ] **Step 5: Commit**

```bash
git add sqlch/sources/spotify.py tests/test_source_spotify.py
git commit -m "sqlch: spotify source uses the user token and lists your playlists and followed artists

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin unstable
```

---

### Task 3: CLI commands

**Files:**
- Modify: `sqlch/cli/main.py`
- Test: `tests/test_cli_spotify.py`

**Interfaces:**
- Consumes: `spotify_auth.login/clear/AuthError` (Task 1), `spotify.client_id()/redirect_port()` (Task 2).
- Produces: `main.spotify_login_cmd(args: list[str]) -> None` and `main.spotify_logout_cmd() -> None`; `dispatch_command` routes `spotify-login` and `spotify-logout`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_spotify.py`:

```python
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from sqlch.cli import main
from sqlch.core import spotify_auth
from sqlch.sources import spotify


class TestSpotifyCli(unittest.TestCase):
    def patched(self, client_id="CID", port=8888):
        return (mock.patch.object(spotify, "client_id", return_value=client_id),
                mock.patch.object(spotify, "redirect_port", return_value=port))

    def run_login(self, args, login=None, **kw):
        a, b = self.patched(**kw)
        with a, b, mock.patch.object(spotify_auth, "login", login or mock.Mock()) as lg, \
                redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            try:
                main.spotify_login_cmd(args)
                code = None
            except SystemExit as e:
                code = e.code
        return lg, code, out.getvalue(), err.getvalue()

    def test_login_uses_client_id_and_configured_port(self):
        lg, code, out, _ = self.run_login([])
        lg.assert_called_once_with("CID", 8888)
        self.assertIsNone(code)
        self.assertIn("logged in", out)

    def test_port_flag_overrides_the_configured_port(self):
        lg, _, _, _ = self.run_login(["--port", "9999"])
        lg.assert_called_once_with("CID", 9999)

    def test_bad_port_is_a_usage_error(self):
        for args in (["--port"], ["--port", "x"]):
            lg, code, _, err = self.run_login(args)
            self.assertEqual(code, 2)
            self.assertIn("usage", err)
            lg.assert_not_called()

    def test_missing_credentials_exit_1_and_name_the_env_file(self):
        lg, code, _, err = self.run_login([], client_id=None)
        self.assertEqual(code, 1)
        self.assertIn("spotify_env", err)
        lg.assert_not_called()

    def test_auth_error_exits_1_with_the_reason(self):
        lg, code, _, err = self.run_login(
            [], login=mock.Mock(side_effect=spotify_auth.AuthError("login timed out")))
        self.assertEqual(code, 1)
        self.assertIn("login timed out", err)

    def test_logout_clears_the_token(self):
        with mock.patch.object(spotify_auth, "clear") as clear, \
                redirect_stdout(io.StringIO()) as out:
            main.spotify_logout_cmd()
        clear.assert_called_once_with()
        self.assertIn("logged out", out.getvalue())

    def test_dispatch_routes_both_commands(self):
        with mock.patch.object(main, "spotify_login_cmd") as login, \
                mock.patch.object(main, "spotify_logout_cmd") as logout:
            main.dispatch_command("spotify-login", ["--port", "1"])
            main.dispatch_command("spotify-logout", [])
        login.assert_called_once_with(["--port", "1"])
        logout.assert_called_once_with()

    def test_help_lists_the_commands(self):
        self.assertIn("sqlch spotify-login", main.HELP)
        self.assertIn("sqlch spotify-logout", main.HELP)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_cli_spotify -v`
Expected: FAIL (`spotify_login_cmd` missing).

- [ ] **Step 3: Implement**

In `sqlch/cli/main.py`, add to `HELP` just before the final `)` of the string (after the `'  sqlch preview <index|url>\n'` line):

```python
    '\n'
    'Spotify:\n'
    '  sqlch spotify-login [--port N]   (log in to see your playlists)\n'
    '  sqlch spotify-logout\n'
```

Add these functions after `status()`:

```python
def spotify_login_cmd(args: list[str]) -> None:
    from sqlch.core import spotify_auth
    from sqlch.sources import spotify
    port = spotify.redirect_port()
    if args[:1] == ['--port']:
        try:
            port = int(args[1])
        except (IndexError, ValueError):
            print('usage: sqlch spotify-login [--port N]', file=sys.stderr)
            sys.exit(2)
    cid = spotify.client_id()
    if cid is None:
        print('sqlch: no Spotify credentials; put SPOTIFY_CLIENT_ID and '
              f'SPOTIFY_CLIENT_SECRET in {spotify.DEFAULT_ENV_FILE}', file=sys.stderr)
        sys.exit(1)
    try:
        spotify_auth.login(cid, port)
    except spotify_auth.AuthError as e:
        print(f'sqlch: spotify login failed: {e}', file=sys.stderr)
        sys.exit(1)
    print('sqlch: logged in to Spotify')


def spotify_logout_cmd() -> None:
    from sqlch.core import spotify_auth
    spotify_auth.clear()
    print('sqlch: logged out of Spotify')
```

At the top of `dispatch_command`, before `if cmd == 'status':`, add:

```python
    if cmd == 'spotify-login':
        spotify_login_cmd(args)
        return
    if cmd == 'spotify-logout':
        spotify_logout_cmd()
        return
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_cli_spotify -v`
Expected: all PASS. Then the whole suite once: `python3 -m unittest discover -s tests -t . 2>&1 | tail -5` (only the 3 known `test_header` errors).

- [ ] **Step 5: Commit**

```bash
git add sqlch/cli/main.py tests/test_cli_spotify.py
git commit -m "sqlch: spotify-login and spotify-logout commands

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push origin unstable
```
