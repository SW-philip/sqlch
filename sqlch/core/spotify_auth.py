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
REQUEST_TIMEOUT = 5  # drop a callback connection that sends nothing for this long
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
    def setup(self):
        self.timeout = REQUEST_TIMEOUT
        super().setup()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/callback":
            self.send_error(404)
            return
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        state = query.get("state")
        if state is None or not secrets.compare_digest(
                state.encode(), self.server.expected_state.encode()):
            self.send_error(400)
            return
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
    server.expected_state = state
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
