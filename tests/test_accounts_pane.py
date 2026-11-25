import unittest
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")

from sqlch.core import accounts, spotify_auth
from sqlch_gui.ui import accounts_pane as ap


def sync(work, done):
    try:
        result, err = work(), None
    except Exception as e:
        result, err = None, str(e)
    done(result, err)


class AccountsPaneTests(unittest.TestCase):
    def setUp(self):
        for target, name, val in ((accounts, "check", mock.Mock()),
                                  (ap, "player_status", lambda: "Paired")):
            p = mock.patch.object(target, name, val)
            p.start()
            self.addCleanup(p.stop)
        accounts._path().unlink(missing_ok=True)
        self.addCleanup(lambda: accounts._path().unlink(missing_ok=True))
        self.changed = mock.Mock()
        self.pane = ap.AccountsPane(self.changed, run_async=sync, opener=mock.Mock())

    def fill(self, **kw):
        for k, v in kw.items():
            self.pane.entries["jellyfin"][k].set_text(v)

    def test_save_checks_first_then_clears_the_secret(self):
        self.fill(server="https://tv", token="tok")
        self.pane.save("jellyfin")
        self.assertEqual(accounts.get("jellyfin"), ("https://tv", "tok"))
        self.assertEqual(self.pane.entries["jellyfin"]["token"].get_text(), "")
        self.assertTrue(self.pane.forget["jellyfin"].get_visible())
        self.changed.assert_called_once()

    def test_failed_check_saves_nothing(self):
        accounts.check.side_effect = accounts.CheckFailed("Can't reach Jellyfin")
        self.fill(server="https://tv", token="tok")
        self.pane.save("jellyfin")
        self.assertIsNone(accounts.get("jellyfin"))
        self.assertIn("Can't reach", self.pane.status["jellyfin"].get_text())
        self.assertEqual(self.pane.entries["jellyfin"]["token"].get_text(), "tok")
        self.changed.assert_not_called()

    def test_stored_secret_is_not_shown(self):
        accounts.save("jellyfin", {"server": "https://tv", "token": "tok"})
        pane = ap.AccountsPane(run_async=sync)
        self.assertEqual(pane.entries["jellyfin"]["server"].get_text(), "https://tv")
        self.assertEqual(pane.entries["jellyfin"]["token"].get_text(), "")

    def test_forget(self):
        accounts.save("jellyfin", {"server": "https://tv", "token": "tok"})
        self.pane.forget_keys("jellyfin")
        self.assertIsNone(accounts.get("jellyfin"))
        self.assertIn("Forgotten", self.pane.status["jellyfin"].get_text())

    def test_failed_login_reports_and_reenables(self):
        with mock.patch.object(ap.spotify, "client_id", return_value="id"), \
                mock.patch.object(spotify_auth, "login",
                                  side_effect=spotify_auth.AuthError("login timed out")):
            self.pane.login()
        self.assertIn("timed out", self.pane.status["login"].get_text())
        self.assertTrue(self.pane.btn_login.get_sensitive())
