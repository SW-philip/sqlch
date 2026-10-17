import unittest
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.source_pane import SourcePane
from sqlch_gui.ui.timefmt import format_duration


def sync(work, done):
    try:
        result, err = work(), None
    except Exception as e:
        result, err = None, str(e)
    done(result, err)


FOLDER = {"source": "fake", "id": "d", "title": "Dir", "kind": "folder", "path": "/d"}
TRACK = {"source": "fake", "id": "t", "title": "Song", "artist": "A", "album": "B",
         "duration": 75, "kind": "track"}


class Fake:
    NAME = "fake"
    HINT = "set it up"

    def __init__(self, ok=True, tree=None):
        self.ok = ok
        self.tree = tree if tree is not None else {None: [FOLDER], "/d": [TRACK]}
        self.browsed = []
        self.searched = []

    def available(self):
        return self.ok

    def browse(self, path=None):
        self.browsed.append(path)
        if isinstance(self.tree, Exception):
            raise self.tree
        return self.tree[path]

    def search(self, q):
        self.searched.append(q)
        return [TRACK]


def make(src, run=sync, play=None):
    return SourcePane(Gtk.Box(), src, run_async=run, play=play or (lambda i: None))


class TestFormat(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(format_duration(None), "")
        self.assertEqual(format_duration(0), "")
        self.assertEqual(format_duration(-3), "")
        self.assertEqual(format_duration(75), "1:15")
        self.assertEqual(format_duration(3725), "1:02:05")


class TestPane(unittest.TestCase):
    def test_on_shown_loads_once(self):
        s = Fake()
        p = make(s)
        p.on_shown()
        p.on_shown()
        self.assertEqual(s.browsed, [None])
        self.assertEqual(p._items, [FOLDER])

    def test_folder_push_and_back(self):
        s = Fake()
        p = make(s)
        p.on_shown()
        p._activate(FOLDER)
        self.assertEqual(p._stack, [("/d", "Dir")])
        self.assertEqual(s.browsed, [None, "/d"])
        self.assertEqual(p._items, [TRACK])
        p.back()
        self.assertEqual(p._stack, [])
        self.assertEqual(p._items, [FOLDER])

    def test_track_plays(self):
        played = []
        p = make(Fake(), play=played.append)
        p.on_shown()
        p._activate(TRACK)
        self.assertEqual(played, [TRACK])
        self.assertEqual(p._stack, [])

    def test_search_and_back(self):
        s = Fake()
        p = make(s)
        p.on_shown()
        p._activate(FOLDER)
        p._search("x")
        self.assertTrue(p._searching)
        self.assertEqual(s.searched, ["x"])
        self.assertEqual(p._items, [TRACK])
        p.entry.set_text("x")
        p.back()
        self.assertFalse(p._searching)
        self.assertEqual(p.entry.get_text(), "")
        self.assertEqual(p._stack, [("/d", "Dir")])
        self.assertEqual(s.browsed[-1], "/d")

    def test_empty_query_leaves_search(self):
        s = Fake()
        p = make(s)
        p.on_shown()
        p._search("x")
        p._search("")
        self.assertFalse(p._searching)
        self.assertEqual(p._items, [FOLDER])

    def test_unavailable(self):
        s = Fake(ok=False)
        p = make(s)
        p.on_shown()
        self.assertEqual(s.browsed, [])
        self.assertEqual(p.status.get_text(), "set it up")
        self.assertTrue(p.status.get_visible())

    def test_error(self):
        p = make(Fake(tree=FileNotFoundError("gone")))
        p.on_shown()
        self.assertEqual(p.status.get_text(), "Couldn't load: gone")

    def test_empty(self):
        p = make(Fake(tree={None: []}))
        p.on_shown()
        self.assertEqual(p.status.get_text(), "Nothing here")

    def _held(self):
        held = []
        p = make(Fake(), run=lambda w, d: held.append((w, d)))
        return p, held

    def test_stale_gen(self):
        p, held = self._held()
        p.on_shown()
        p._gen += 1
        work, done = held[0]
        done(work(), None)
        self.assertEqual(p._items, [])

    def test_hidden_invalidates(self):
        p, held = self._held()
        p.on_shown()
        p.on_hidden()
        work, done = held[0]
        done(work(), None)
        self.assertEqual(p._items, [])

    def test_reopen_after_hidden_first_load(self):
        p, held = self._held()
        p.on_shown()
        p.on_hidden()
        work, done = held.pop(0)
        done(work(), None)
        self.assertEqual(p._items, [])
        p.on_shown()
        work, done = held.pop(0)
        done(work(), None)
        self.assertEqual(p._items, [FOLDER])

    def test_reopen_after_hidden_folder_and_search(self):
        s = Fake()
        held = []
        p = make(s, run=lambda w, d: held.append((w, d)))

        def flush():
            while held:
                w, d = held.pop(0)
                d(w(), None)

        p.on_shown()
        flush()
        p._activate(FOLDER)
        p.on_hidden()
        flush()
        self.assertEqual(p._items, [FOLDER])
        p.on_shown()
        flush()
        self.assertEqual(p._items, [TRACK])
        p._search("q")
        p.on_hidden()
        flush()
        p.on_shown()
        flush()
        self.assertEqual(s.searched, ["q", "q"])
        self.assertEqual(p._items, [TRACK])

    def test_rendered_not_reloaded(self):
        s = Fake()
        p = make(s)
        p.on_shown()
        p.on_hidden()
        p.on_shown()
        self.assertEqual(s.browsed, [None])


class TestPlayErrors(unittest.TestCase):
    def _play_with(self, resp):
        from unittest import mock
        p = make(Fake(), play=None)
        p._play = p._daemon_play
        p.on_shown()
        with mock.patch("sqlch_gui.ui.source_pane.daemon.send", return_value=resp):
            p._activate(TRACK)
        return p

    def test_failures(self):
        for resp, text in ((None, "daemon not running"), ({"ok": False, "error": "x"}, "x")):
            p = self._play_with(resp)
            self.assertEqual(p.status.get_text(), f"Couldn't play: {text}")
            self.assertTrue(p.status.get_visible())

    def test_exception(self):
        def boom(item):
            raise OSError("bad")
        p = make(Fake(), play=boom)
        p.on_shown()
        p._activate(TRACK)
        self.assertEqual(p.status.get_text(), "Couldn't play: bad")
        self.assertTrue(p.status.get_visible())

    def test_success_leaves_status(self):
        p = self._play_with({"ok": True})
        self.assertFalse(p.status.get_visible())
        self.assertEqual(p._items, [FOLDER])


if __name__ == "__main__":
    unittest.main()


class TestAvailableRaises(unittest.TestCase):
    def test_raising_available_shows_hint(self):
        src = Fake()
        src.available = mock.Mock(side_effect=TypeError("bad config"))
        pane = make(src)
        with self.assertLogs("sqlch.sources", "ERROR"):
            pane.on_shown()
        self.assertEqual(pane.status.get_text(), src.HINT)
        self.assertTrue(pane.status.get_visible())
