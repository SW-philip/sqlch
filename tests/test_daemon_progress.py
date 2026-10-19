import unittest
from unittest import mock

from sqlch.core import daemon

VID = {"source": "youtube", "id": "abc", "kind": "video", "title": "t"}


def _cur(item=VID):
    return {"type": "item", "item": item}


class TestTrackOnce(unittest.TestCase):
    def run_once(self, cur, prog=(120.0, 1000.0)):
        with mock.patch.object(daemon.player, "current", return_value=cur), \
             mock.patch.object(daemon.player, "item_progress", return_value=prog), \
             mock.patch.object(daemon.progress, "record") as rec:
            daemon.track_once()
        return rec

    def test_records_video_playhead(self):
        self.run_once(_cur()).assert_called_once_with("youtube", "abc", 120.0, 1000.0)

    def test_ignores_non_video_and_radio_and_idle(self):
        self.run_once(_cur({**VID, "kind": "track"})).assert_not_called()
        self.run_once({"type": "station"}).assert_not_called()
        self.run_once(None).assert_not_called()

    def test_ignores_unloaded_player(self):
        self.run_once(_cur(), prog=(None, None)).assert_not_called()
        self.run_once(_cur(), prog=(0, None)).assert_not_called()


class TestPlayItemResume(unittest.TestCase):
    def play(self, resume, row):
        src = mock.Mock()
        src.resolve.return_value = "target"
        with mock.patch.dict(daemon.sources.REGISTRY, {"youtube": src}), \
             mock.patch.object(daemon.progress, "get", return_value=row), \
             mock.patch.object(daemon, "track_once"), \
             mock.patch.object(daemon.player, "play_target") as pt:
            resp = daemon._handle({"cmd": "play_item", "item": VID, "resume": resume})
        return resp, pt

    def test_resume_starts_at_saved_point(self):
        resp, pt = self.play(True, {"position": 300, "watched": False})
        self.assertTrue(resp["ok"])
        pt.assert_called_once_with("target", VID, start=300.0)

    def test_start_over_ignores_saved_point(self):
        _, pt = self.play(False, {"position": 300, "watched": False})
        pt.assert_called_once_with("target", VID, start=None)

    def test_resume_with_nothing_saved_starts_at_zero(self):
        _, pt = self.play(True, None)
        pt.assert_called_once_with("target", VID, start=None)


class TestMarkWatched(unittest.TestCase):
    def test_mark(self):
        with mock.patch.object(daemon.progress, "mark") as m:
            self.assertEqual(daemon._handle({"cmd": "mark_watched", "item": VID,
                                             "watched": False}), {"ok": True})
        m.assert_called_once_with("youtube", "abc", False)

    def test_rejects_missing_item(self):
        self.assertFalse(daemon._handle({"cmd": "mark_watched"})["ok"])


if __name__ == "__main__":
    unittest.main()
