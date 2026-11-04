import unittest
from unittest import mock

from sqlch.core import mpris_daemon


class TestMprisTransport(unittest.TestCase):
    def setUp(self):
        self.t = mock.patch.object(mpris_daemon, "transport").start()
        self.addCleanup(mock.patch.stopall)
        self.m = mpris_daemon.SQLCHMPRIS()

    def test_next_and_previous_call_the_transport(self):
        self.m.Next()
        self.t.next_cmd.assert_called_once_with()
        self.m.Previous()
        self.t.prev_cmd.assert_called_once_with()

    def test_can_go_follows_the_transport(self):
        self.t.can_go_next.return_value = True
        self.t.can_go_previous.return_value = False
        self.assertTrue(self.m.CanGoNext)
        self.assertFalse(self.m.CanGoPrevious)

    def test_get_all_reports_them(self):
        self.t.can_go_next.return_value = True
        self.t.can_go_previous.return_value = True
        props = self.m.GetAll("org.mpris.MediaPlayer2.Player")
        self.assertTrue(props["CanGoNext"].get_boolean())

    def test_introspection_lists_the_methods(self):
        self.assertIn('<method name="Next"/>', mpris_daemon.MPRIS_XML)
        self.assertIn('<method name="Previous"/>', mpris_daemon.MPRIS_XML)


if __name__ == "__main__":
    unittest.main()
