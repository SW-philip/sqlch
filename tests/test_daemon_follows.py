import unittest
from unittest import mock

from sqlch.core import daemon

CID = "UC" + "a" * 22


class TestDaemonFollowCommands(unittest.TestCase):
    def test_toggle_favorite(self):
        item = {"source": "youtube", "id": "x"}
        with mock.patch.object(daemon.follows, "toggle_favorite", return_value=True) as t:
            self.assertEqual(daemon._handle({"cmd": "toggle_favorite", "item": item}),
                             {"ok": True, "favorite": True})
        t.assert_called_once_with(item)

    def test_toggle_favorite_rejects_bad_input(self):
        self.assertFalse(daemon._handle({"cmd": "toggle_favorite"})["ok"])
        resp = daemon._handle({"cmd": "toggle_favorite", "item": {"title": "no id"}})
        self.assertFalse(resp["ok"])

    def test_follow(self):
        with mock.patch.object(daemon.follows, "follow") as f:
            resp = daemon._handle({"cmd": "follow", "channel_id": CID, "name": "Chan"})
        self.assertEqual(resp, {"ok": True})
        f.assert_called_once_with(CID, "Chan")

    def test_follow_rejects_invalid_channel_id(self):
        with mock.patch.object(daemon.follows, "follow") as f:
            resp = daemon._handle({"cmd": "follow", "channel_id": "bad", "name": "x"})
        self.assertFalse(resp["ok"])
        f.assert_not_called()

    def test_follow_without_name_uses_the_id(self):
        with mock.patch.object(daemon.follows, "follow") as f:
            daemon._handle({"cmd": "follow", "channel_id": CID})
        f.assert_called_once_with(CID, CID)

    def test_unfollow(self):
        with mock.patch.object(daemon.follows, "unfollow") as u:
            self.assertEqual(daemon._handle({"cmd": "unfollow", "channel_id": CID}),
                             {"ok": True})
        u.assert_called_once_with(CID)

    def test_drain_notices(self):
        with mock.patch.object(daemon.watcher, "drain", return_value=["a", "b"]):
            self.assertEqual(daemon._handle({"cmd": "drain_notices"}),
                             {"ok": True, "notices": ["a", "b"]})

    def test_podcast_follow(self):
        item = {"feed_url": "https://f/a", "title": "A"}
        with mock.patch.object(daemon.follows, "follow_podcast") as f:
            self.assertEqual(daemon._handle({"cmd": "podcast_follow", "item": item}),
                             {"ok": True})
        f.assert_called_once_with(item)

    def test_podcast_follow_rejects_non_http_feeds(self):
        with mock.patch.object(daemon.follows, "follow_podcast") as f:
            for msg in ({"cmd": "podcast_follow"},
                        {"cmd": "podcast_follow", "item": "x"},
                        {"cmd": "podcast_follow", "item": {"feed_url": "file:///etc/passwd"}}):
                self.assertFalse(daemon._handle(msg)["ok"])
        f.assert_not_called()

    def test_podcast_unfollow(self):
        with mock.patch.object(daemon.follows, "unfollow_podcast") as u:
            self.assertEqual(daemon._handle({"cmd": "podcast_unfollow",
                                             "feed_url": "https://f/a"}), {"ok": True})
            self.assertFalse(daemon._handle({"cmd": "podcast_unfollow", "feed_url": 3})["ok"])
        u.assert_called_once_with("https://f/a")

if __name__ == "__main__":
    unittest.main()
