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
