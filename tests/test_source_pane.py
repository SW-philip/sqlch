import unittest

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


if __name__ == "__main__":
    unittest.main()
