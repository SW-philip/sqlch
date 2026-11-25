import io
import stat
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

from sqlch.core import accounts, spotify_auth
from sqlch.sources import _podcast_dirs, jellyfin, spotify

SP = {"client_id": "id", "client_secret": "sec"}
JF = {"server": "https://tv.example", "token": "tok"}


def clean():
    accounts._path().unlink(missing_ok=True)
    spotify_auth.clear()


class Base(unittest.TestCase):
    def setUp(self):
        clean()
        self.addCleanup(clean)
        p = mock.patch.object(accounts, "cache_dir", lambda: accounts.data_dir())
        p.start()
        self.addCleanup(p.stop)


class StoreTests(Base):
    def test_round_trip_is_private(self):
        accounts.save("spotify", SP)
        self.assertEqual(accounts.get("spotify"), ("id", "sec"))
        self.assertEqual(stat.S_IMODE(accounts._path().stat().st_mode), 0o600)

    def test_partial_or_damaged_entry_is_none(self):
        with self.assertRaises(ValueError):
            accounts.save("spotify", {"client_id": "id"})
        accounts._path().write_text('{"spotify": {"client_id": 3}}')
        self.assertIsNone(accounts.get("spotify"))
        accounts._path().write_text("[")
        self.assertIsNone(accounts.get("spotify"))

    def test_newline_refused(self):
        with self.assertRaises(ValueError):
            accounts.save("jellyfin", {**JF, "token": "a\r\nX: y"})

    def test_forget_keeps_other_services(self):
        accounts.save("spotify", SP)
        accounts.save("jellyfin", JF)
        accounts.forget("spotify")
        self.assertIsNone(accounts.get("spotify"))
        self.assertEqual(accounts.get("jellyfin"), ("https://tv.example", "tok"))

    def test_new_spotify_app_drops_tokens_but_same_keys_do_not(self):
        accounts.save("spotify", SP)
        tok = accounts.cache_dir() / "spotify_token.json"
        for values, kept in ((SP, True), ({**SP, "client_id": "other"}, False)):
            tok.write_text("{}")
            spotify_auth._save({"refresh_token": "r"})
            accounts.save("spotify", values)
            self.assertEqual((tok.exists(), spotify_auth.logged_in()), (kept, kept))


class LookupTests(Base):
    def test_stored_beats_environment(self):
        accounts.save("spotify", SP)
        accounts.save("podcastindex", {"key": "k", "secret": "s"})
        with mock.patch.dict("os.environ", {
                "SPOTIFY_CLIENT_ID": "e", "SPOTIFY_CLIENT_SECRET": "e",
                "PODCASTINDEX_API_KEY": "e", "PODCASTINDEX_API_SECRET": "e"}):
            self.assertEqual(spotify._credentials(), ("id", "sec"))
            self.assertEqual(_podcast_dirs.pi_credentials(), ("k", "s"))

    def test_jellyfin_address_and_key_come_together(self):
        with mock.patch.object(jellyfin, "source_config", return_value={
                "server": "https://cfg", "token_file": "/nonexistent"}):
            self.assertEqual(jellyfin._server(), "https://cfg")
            accounts.save("jellyfin", JF)
            self.assertEqual((jellyfin._server(), jellyfin._token()),
                             ("https://tv.example", "tok"))


class CheckTests(Base):
    def fails(self, service, values, text, **kw):
        with mock.patch.object(accounts, "urlopen", **kw) as m, \
                self.assertRaises(accounts.CheckFailed) as e:
            accounts.check(service, values)
        self.assertIn(text, str(e.exception))
        return m

    def test_rejected_and_unreachable(self):
        self.fails("spotify", SP, "rejected",
                   side_effect=HTTPError("u", 401, "no", {}, io.BytesIO()))
        self.fails("jellyfin", JF, "Can't reach", side_effect=URLError("x"))

    def test_plain_http_never_sends_the_key(self):
        m = self.fails("jellyfin", {**JF, "server": "http://tv.example"}, "https")
        m.assert_not_called()

    def test_empty_field(self):
        self.fails("spotify", {"client_id": "x"}, "every field")

    def test_accepted(self):
        with mock.patch.object(accounts, "urlopen") as m:
            for s, v in (("spotify", SP), ("jellyfin", JF),
                         ("podcastindex", {"key": "k", "secret": "s"})):
                accounts.check(s, v)
        self.assertEqual(m.call_count, 3)
