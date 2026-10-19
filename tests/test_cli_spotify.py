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

    def test_out_of_range_port_is_a_usage_error(self):
        for port in ("0", "-5", "65536", "70000"):
            lg, code, _, err = self.run_login(["--port", port])
            self.assertEqual(code, 2, port)
            self.assertIn("usage", err, port)
            lg.assert_not_called()

    def test_port_edges_are_accepted(self):
        for port in (1, 65535):
            lg, code, _, _ = self.run_login(["--port", str(port)])
            lg.assert_called_once_with("CID", port)
            self.assertIsNone(code)

    def test_unknown_args_are_usage_errors(self):
        for args in (["--prot", "9999"], ["--port=9999"],
                     ["--port", "9999", "extra"], ["extra"]):
            lg, code, _, err = self.run_login(args)
            self.assertEqual(code, 2, args)
            self.assertIn("usage", err, args)
            lg.assert_not_called()

    def test_out_of_range_configured_port_exits_2(self):
        for port in (0, 70000):
            lg, code, _, err = self.run_login([], port=port)
            self.assertEqual(code, 2, port)
            self.assertIn("sources.spotify.redirect_port", err)
            lg.assert_not_called()

    def test_logout_extra_args_are_usage_error(self):
        with mock.patch.object(spotify_auth, "clear") as clear, \
                redirect_stdout(io.StringIO()), \
                redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                main.dispatch_command("spotify-logout", ["extra"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("usage", err.getvalue())
        clear.assert_not_called()

    def test_help_lists_the_commands(self):
        self.assertIn("sqlch spotify-login", main.HELP)
        self.assertIn("sqlch spotify-logout", main.HELP)


if __name__ == "__main__":
    unittest.main()
