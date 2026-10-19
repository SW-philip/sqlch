import unittest
from unittest import mock

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sqlch_gui.ui.source_pane import SourcePane
from sqlch_gui.ui.timefmt import format_date, format_duration


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


class FakeStore:
    def __init__(self, favs=(), followed=(), feeds=()):
        self.favs = list(favs)
        self.followed = set(followed)
        self.feeds = set(feeds)

    def list_favorites(self, source):
        return [f for f in self.favs if f["source"] == source]

    def favorite_ids(self, source):
        return {f["id"] for f in self.list_favorites(source)}

    def followed_ids(self):
        return set(self.followed)

    def followed_feeds(self):
        return set(self.feeds)


def make(src, run=sync, play=None, store=None, send=None):
    return SourcePane(Gtk.Box(), src, run_async=run, play=play or (lambda i: None),
                      store=store or FakeStore(),
                      send=send or (lambda m: {"ok": True}))


class TestFormat(unittest.TestCase):
    def test_date_is_the_utc_calendar_day(self):
        self.assertEqual(format_date(1792108800), "Oct 16, 2026")
        self.assertEqual(format_date(None), "")
        self.assertEqual(format_date(0), "")

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
        self.assertFalse(p.section_row.get_visible())

    def test_available_shows_section_row(self):
        p = make(Fake(tree={None: []}))
        p.on_shown()
        self.assertTrue(p.section_row.get_visible())

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


class Sectioned(Fake):
    def __init__(self):
        super().__init__(tree={"section:a": [FOLDER], "section:b": [TRACK], "/d": [TRACK]})

    def sections(self):
        return [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]


VIDEO = {"source": "fake", "id": "v", "title": "Vid", "artist": "Chan",
         "kind": "video", "channel_id": "UC1"}
SHOW = {"source": "fake", "id": "https://f/a", "title": "Show", "kind": "folder",
        "path": "feed:https://f/a", "feed_url": "https://f/a", "genre": "Comedy",
        "providers": ["apple"]}


class TestSections(unittest.TestCase):
    def test_source_without_sections_shows_browse_and_favorites(self):
        p = make(Fake())
        self.assertEqual([s["id"] for s in p._sections], ["browse", "favorites"])
        p.on_shown()
        self.assertEqual(p._section, "browse")

    def test_first_section_loads_by_default(self):
        s = Sectioned()
        p = make(s)
        p.on_shown()
        self.assertEqual(s.browsed, ["section:a"])
        self.assertEqual(p._items, [FOLDER])

    def test_selecting_a_section_loads_it_and_resets_navigation(self):
        s = Sectioned()
        p = make(s)
        p.on_shown()
        p._activate(FOLDER)
        self.assertEqual(p._stack, [("/d", "Dir")])
        p._select_section("b")
        self.assertEqual(p._stack, [])
        self.assertEqual(s.browsed[-1], "section:b")
        self.assertEqual(p._items, [TRACK])

    def test_search_then_clear_returns_to_the_section(self):
        s = Sectioned()
        p = make(s)
        p.on_shown()
        p._select_section("b")
        p._search("q")
        self.assertTrue(p._searching)
        p._search("")
        self.assertFalse(p._searching)
        self.assertEqual(s.browsed[-1], "section:b")

    def test_favorites_come_from_the_store_not_the_source(self):
        s = Sectioned()
        fav = {**TRACK, "source": "fake"}
        p = make(s, store=FakeStore(favs=[fav, {**TRACK, "source": "other", "id": "z"}]))
        p.on_shown()
        p._select_section("favorites")
        self.assertEqual(p._items, [fav])
        self.assertNotIn("section:favorites", s.browsed)

    def test_active_pill_follows_the_section(self):
        p = make(Sectioned())
        p.on_shown()
        self.assertTrue(p._pills["a"].has_css_class("active"))
        p._select_section("b")
        self.assertFalse(p._pills["a"].has_css_class("active"))
        self.assertTrue(p._pills["b"].has_css_class("active"))


class TestStarAndFollow(unittest.TestCase):
    def test_star_state_comes_from_the_store(self):
        p = make(Fake(tree={None: [TRACK]}), store=FakeStore(favs=[TRACK]))
        p.on_shown()
        self.assertEqual(p._fav_ids, {"t"})

    def test_toggle_favorite_sends_to_daemon_and_updates_button(self):
        sent = []
        p = make(Fake(), send=lambda m: sent.append(m) or {"ok": True, "favorite": True})
        p.on_shown()
        btn = Gtk.Button(label="☆")
        p._toggle_favorite(TRACK, btn)
        self.assertEqual(sent, [{"cmd": "toggle_favorite", "item": TRACK}])
        self.assertEqual(btn.get_label(), "★")
        self.assertIn("t", p._fav_ids)
        sent.clear()
        p._send = lambda m: {"ok": True, "favorite": False}
        p._toggle_favorite(TRACK, btn)
        self.assertEqual(btn.get_label(), "☆")
        self.assertNotIn("t", p._fav_ids)

    def test_stale_load_does_not_overwrite_marks(self):
        held = []
        p = make(Fake(), run=lambda w, d: held.append((w, d)), store=FakeStore())
        p.on_shown()
        work, done = held.pop(0)
        p._fav_ids = {"t"}
        p._followed = {"UC1"}
        p._gen += 1
        done(work(), None)
        self.assertEqual(p._fav_ids, {"t"})
        self.assertEqual(p._followed, {"UC1"})

    def test_toggle_favorite_failure_shows_status(self):
        p = make(Fake(), send=lambda m: None)
        p.on_shown()
        p._toggle_favorite(TRACK, Gtk.Button(label="☆"))
        self.assertIn("Couldn't update favorites", p.status.get_text())

    def test_unfavoriting_in_favorites_section_refreshes_the_list(self):
        store = FakeStore(favs=[TRACK])
        p = make(Fake(), store=store, send=lambda m: {"ok": True, "favorite": False})
        p.on_shown()
        p._select_section("favorites")
        self.assertEqual(p._items, [TRACK])
        store.favs.clear()
        p._toggle_favorite(TRACK, Gtk.Button(label="★"))
        self.assertEqual(p._items, [])

    def test_follow_sends_channel_id_and_channel_name(self):
        sent = []
        p = make(Fake(tree={None: [VIDEO]}),
                 send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        btn = Gtk.Button(label="Follow")
        p._toggle_follow(VIDEO, btn)
        self.assertEqual(sent, [{"cmd": "follow", "channel_id": "UC1", "name": "Chan"}])
        self.assertEqual(btn.get_label(), "Unfollow")
        self.assertIn("UC1", p._followed)

    def test_unfollow_sends_unfollow(self):
        sent = []
        p = make(Fake(tree={None: [VIDEO]}), store=FakeStore(followed=["UC1"]),
                 send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        btn = Gtk.Button(label="Unfollow")
        p._toggle_follow(VIDEO, btn)
        self.assertEqual(sent, [{"cmd": "unfollow", "channel_id": "UC1"}])
        self.assertEqual(btn.get_label(), "Follow")
        self.assertNotIn("UC1", p._followed)

    def test_channel_folder_uses_its_title_as_the_name(self):
        sent = []
        chan = {"source": "fake", "id": "UC1", "title": "Chan Folder", "kind": "folder",
                "path": "/c", "channel_id": "UC1"}
        p = make(Fake(), send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        p._toggle_follow(chan, Gtk.Button(label="Follow"))
        self.assertEqual(sent[0]["name"], "Chan Folder")

    def test_rows_only_offer_follow_when_there_is_a_channel(self):
        p = make(Fake())
        labels = []

        def collect(widget):
            child = widget.get_first_child()
            while child:
                if isinstance(child, Gtk.Button):
                    labels.append(child.get_label())
                collect(child)
                child = child.get_next_sibling()

        collect(p._build_row(TRACK))
        self.assertEqual(labels, ["☆"])
        labels.clear()
        collect(p._build_row(VIDEO))
        self.assertEqual(labels, ["☆", "○", "Follow"])


class FakeWatch:
    def __init__(self, rows=None):
        self.rows = rows or {}

    def read_all(self):
        return dict(self.rows)

    def get(self, source, id):
        return self.rows.get(f"{source}:{id}")


def vid(id, title, date=None):
    return {"source": "fake", "id": id, "title": title, "artist": "Chan",
            "kind": "video", "duration": 1200, "date": date}


def labels_of(widget, out=None):
    out = [] if out is None else out
    child = widget.get_first_child()
    while child:
        if isinstance(child, Gtk.Label):
            out.append(child)
        labels_of(child, out)
        child = child.get_next_sibling()
    return out


def button_labels(widget, out=None):
    out = [] if out is None else out
    child = widget.get_first_child()
    while child:
        if isinstance(child, Gtk.Button):
            out.append(child.get_label())
        button_labels(child, out)
        child = child.get_next_sibling()
    return out


class TestWatchedUi(unittest.TestCase):
    def pane(self, rows=None, play=None, send=None, tree=None):
        src = Fake(tree=tree or {None: [vid("a", "Alpha", 1792108800)]})
        src.HAS_DATES = True
        p = SourcePane(Gtk.Box(), src, run_async=sync, play=play or (lambda i, **k: None),
                       store=FakeStore(), send=send or (lambda m: {"ok": True}),
                       watch=FakeWatch(rows))
        p.on_shown()
        return p

    def test_unwatched_row_has_no_banner_or_bar(self):
        p = self.pane()
        refs = p._row_refs["fake:a"]
        self.assertFalse(refs["banner"].get_visible())
        self.assertFalse(refs["bar"].get_visible())
        self.assertEqual(refs["toggle"].get_label(), "○")

    def test_watched_row_shows_banner(self):
        p = self.pane({"fake:a": {"watched": True, "position": 0, "duration": 1200}})
        refs = p._row_refs["fake:a"]
        self.assertTrue(refs["banner"].get_visible())
        self.assertEqual(refs["banner"].get_label(), "WATCHED")
        self.assertEqual(refs["note"].get_text(), "Watched")
        self.assertEqual(refs["toggle"].get_label(), "✓")

    def test_partial_row_shows_how_much_was_watched(self):
        p = self.pane({"fake:a": {"watched": False, "position": 300, "duration": 1200}})
        refs = p._row_refs["fake:a"]
        self.assertFalse(refs["banner"].get_visible())
        self.assertTrue(refs["bar"].get_visible())
        self.assertAlmostEqual(refs["bar"].get_fraction(), 0.25)
        self.assertEqual(refs["note"].get_text(), "5:00 of 20:00 watched")

    def test_row_shows_upload_date(self):
        p = self.pane()
        texts = [l.get_text() for l in labels_of(p.list)]
        self.assertIn("Chan · Oct 16, 2026", texts)

    def test_oldest_first_orders_by_date_with_undated_last(self):
        tree = {None: [vid("n", "Newest", 300 * 86400), vid("u", "Undated"),
                       vid("o", "Oldest", 100 * 86400)]}
        p = self.pane(tree=tree)

        def titles():
            names = {"Newest", "Undated", "Oldest"}
            return [l.get_text() for l in labels_of(p.list) if l.get_text() in names]

        self.assertEqual(titles(), ["Newest", "Undated", "Oldest"])
        p.btn_order.set_active(True)
        self.assertEqual(titles(), ["Oldest", "Newest", "Undated"])

    def test_click_without_saved_point_just_plays(self):
        played = []
        p = self.pane(play=lambda i, **k: played.append((i["id"], k)))
        with mock.patch.object(p, "_offer_resume") as offer:
            p._activate(vid("a", "Alpha"), Gtk.Box())
        offer.assert_not_called()
        self.assertEqual(played, [("a", {})])

    def test_click_with_saved_point_offers_resume_or_restart(self):
        played = []
        rows = {"fake:a": {"watched": False, "position": 300, "duration": 1200}}
        p = self.pane(rows, play=lambda i, **k: played.append(k))
        anchor = Gtk.Box()
        with mock.patch.object(p, "_offer_resume") as offer:
            p._activate(vid("a", "Alpha"), anchor)
        offer.assert_called_once_with(vid("a", "Alpha"), 300.0, anchor)
        self.assertEqual(played, [])
        pop = mock.Mock()
        p._start(vid("a", "Alpha"), True, pop)
        p._start(vid("a", "Alpha"), False, pop)
        self.assertEqual(played, [{"resume": True}, {}])

    def test_watched_video_replays_from_the_start(self):
        played = []
        rows = {"fake:a": {"watched": True, "position": 0, "duration": 1200}}
        p = self.pane(rows, play=lambda i, **k: played.append(k))
        with mock.patch.object(p, "_offer_resume") as offer:
            p._activate(vid("a", "Alpha"), Gtk.Box())
        offer.assert_not_called()
        self.assertEqual(played, [{}])

    def test_toggle_sends_mark_and_refreshes(self):
        sent = []
        p = self.pane(send=lambda m: sent.append(m) or {"ok": True})
        item = vid("a", "Alpha")
        p._toggle_watched(item)
        self.assertEqual(sent[0], {"cmd": "mark_watched", "item": item, "watched": True})
        p._watch.rows["fake:a"] = {"watched": True, "position": 0, "duration": 1200}
        p._refresh_progress()
        p._toggle_watched(item)
        self.assertFalse(sent[1]["watched"])

    def test_resume_reaches_the_daemon_message(self):
        with mock.patch("sqlch_gui.ui.source_pane.daemon.send",
                        return_value={"ok": True}) as send:
            SourcePane._daemon_play({"source": "fake", "id": "a"}, resume=True)
        self.assertTrue(send.call_args[0][0]["resume"])


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


class TestPlayErrorClears(unittest.TestCase):
    def _pane(self, src, outcomes):
        def play(item):
            r = outcomes.pop(0)
            if r:
                raise RuntimeError(r)
        return make(src, play=play)

    def test_success_clears_play_error(self):
        pane = self._pane(Fake(), ["nope", None])
        pane.on_shown()
        pane._activate(TRACK)
        self.assertEqual(pane.status.get_text(), "Couldn't play: nope")
        self.assertTrue(pane.status.get_visible())
        pane._activate(TRACK)
        self.assertFalse(pane.status.get_visible())

    def test_success_keeps_hint(self):
        pane = self._pane(Fake(ok=False), [None])
        pane.on_shown()
        pane._activate(TRACK)
        self.assertEqual(pane.status.get_text(), "set it up")
        self.assertTrue(pane.status.get_visible())


class TestPodcastFollow(unittest.TestCase):
    def test_feed_rows_offer_follow(self):
        p = make(Fake(tree={None: [SHOW]}))
        p.on_shown()
        self.assertIn("Follow", button_labels(p._build_row(SHOW)))
        p = make(Fake(tree={None: [SHOW]}), store=FakeStore(feeds=["https://f/a"]))
        p.on_shown()
        self.assertIn("Unfollow", button_labels(p._build_row(SHOW)))

    def test_follow_sends_podcast_follow_with_the_item(self):
        sent = []
        p = make(Fake(tree={None: [SHOW]}), send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        btn = Gtk.Button(label="Follow")
        p._toggle_follow(SHOW, btn)
        self.assertEqual(sent, [{"cmd": "podcast_follow", "item": SHOW}])
        self.assertEqual(btn.get_label(), "Unfollow")

    def test_unfollow_in_following_reloads(self):
        sent = []
        src = Fake(tree={"section:following": [SHOW]})
        src.sections = lambda: [{"id": "following", "title": "FOLLOWING"}]
        p = make(src, store=FakeStore(feeds=["https://f/a"]),
                 send=lambda m: sent.append(m) or {"ok": True})
        p.on_shown()
        src.tree["section:following"] = []
        p._toggle_follow(SHOW, Gtk.Button(label="Unfollow"))
        self.assertEqual(sent, [{"cmd": "podcast_unfollow", "feed_url": "https://f/a"}])
        self.assertEqual(p._items, [])


class TestSearchWarning(unittest.TestCase):
    def test_warning_shows_in_status(self):
        src = Fake()
        src.last_warning = lambda: "Podcast Index unavailable"
        p = make(src)
        p.on_shown()
        p._search("x")
        self.assertTrue(p.status.get_visible())
        self.assertEqual(p.status.get_text(), "Podcast Index unavailable")

    def test_no_warning_hook_is_fine(self):
        p = make(Fake())
        p.on_shown()
        p._search("x")
        self.assertFalse(p.status.get_visible())
