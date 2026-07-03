import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlch.core import recorder


class TestSanitizeFilename(unittest.TestCase):
    def test_replaces_path_separators(self):
        self.assertEqual(recorder.sanitize_filename("AC/DC - Back In Black"),
                         "AC-DC - Back In Black")

    def test_strips_control_chars_and_collapses_whitespace(self):
        self.assertEqual(recorder.sanitize_filename("a\x00b   c\n"), "ab c")

    def test_strips_leading_trailing_dots_and_spaces(self):
        self.assertEqual(recorder.sanitize_filename(" .hidden. "), "hidden")

    def test_empty_becomes_untitled(self):
        self.assertEqual(recorder.sanitize_filename("///"), "untitled")

    def test_caps_length(self):
        self.assertEqual(len(recorder.sanitize_filename("x" * 500)), 120)


class TestExtForCodec(unittest.TestCase):
    def test_known_codecs(self):
        self.assertEqual(recorder.ext_for_codec("aac"), ".m4a")
        self.assertEqual(recorder.ext_for_codec("mp3"), ".mp3")
        self.assertEqual(recorder.ext_for_codec("vorbis"), ".ogg")
        self.assertEqual(recorder.ext_for_codec("opus"), ".opus")

    def test_unknown_or_none_falls_back_to_mka(self):
        self.assertEqual(recorder.ext_for_codec("wma9"), ".mka")
        self.assertEqual(recorder.ext_for_codec(None), ".mka")

    def test_case_insensitive(self):
        self.assertEqual(recorder.ext_for_codec("AAC"), ".m4a")


class TestUniquePath(unittest.TestCase):
    def test_returns_path_unchanged_when_free(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.m4a"
            self.assertEqual(recorder.unique_path(p), p)

    def test_suffixes_on_collision(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.m4a"
            p.touch()
            self.assertEqual(recorder.unique_path(p), Path(td) / "a (2).m4a")
            (Path(td) / "a (2).m4a").touch()
            self.assertEqual(recorder.unique_path(p), Path(td) / "a (3).m4a")


class TestFormatTracklist(unittest.TestCase):
    def test_formats_entries(self):
        out = recorder.format_tracklist([
            (0.0, "Kraftwerk", "Autobahn"),
            (75.4, None, "Station Ident"),
        ])
        self.assertEqual(out, "[00:00] Kraftwerk - Autobahn\n[01:15] Station Ident\n")

    def test_empty_list(self):
        self.assertEqual(recorder.format_tracklist([]), "")


_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _synth_aac(dest: Path) -> None:
    """1 second of sine, AAC in an ADTS stream — same shape as a radio dump."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "aac", "-f", "adts", str(dest)],
        check=True,
    )


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg/ffprobe not on PATH")
class TestFinalize(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        patcher = mock.patch.object(
            recorder.config, "load",
            return_value={"recordings_dir": str(self.root)},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._td.cleanup)

    def test_finalize_remuxes_tags_and_removes_raw(self):
        raw = self.root / ".incoming" / "rec-x-0.dump"
        raw.parent.mkdir(parents=True)
        _synth_aac(raw)

        dest = recorder._finalize(
            raw, "KEXP 90.3", {"artist": "Kraftwerk", "title": "Autobahn"},
            "Kraftwerk - Autobahn",
        )
        self.assertIsNotNone(dest)
        self.assertEqual(dest, self.root / "KEXP 90.3" / "Kraftwerk - Autobahn.m4a")
        self.assertTrue(dest.exists())
        self.assertFalse(raw.exists())

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags=artist,title",
             "-of", "default=noprint_wrappers=1", str(dest)],
            capture_output=True, text=True,
        ).stdout
        self.assertIn("artist=Kraftwerk", probe)
        self.assertIn("title=Autobahn", probe)

    def test_finalize_partial_suffix(self):
        raw = self.root / ".incoming" / "rec-x-1.dump"
        raw.parent.mkdir(parents=True)
        _synth_aac(raw)
        dest = recorder._finalize(raw, "KEXP 90.3", {}, "Some Song", partial=True)
        self.assertEqual(dest.name, "Some Song (partial).m4a")

    def test_finalize_empty_raw_returns_none(self):
        raw = self.root / ".incoming" / "empty.dump"
        raw.parent.mkdir(parents=True)
        raw.touch()
        self.assertIsNone(recorder._finalize(raw, "X", {}, "Y"))
        self.assertFalse(raw.exists())


class FakeMpv:
    """Stands in for sqlch.core.player: records set_property calls."""

    def __init__(self, playing=True, icy=None):
        self._playing = playing
        self._icy = icy
        self.props: list[tuple] = []

    class _Sock:
        def __init__(self, exists): self._e = exists
        def exists(self): return self._e

    def mpv_socket(self):
        return self._Sock(self._playing)

    def mpv_get(self, prop):
        if not self._playing:
            return None
        if prop == "pid":
            return 4242
        if prop == "metadata":
            return {"icy-title": self._icy} if self._icy else {}
        if prop == "filtered-metadata":
            return {"icy-genre": "electronic"}
        return None

    def mpv_command(self, *parts):
        self.props.append(parts)

    def stream_record_values(self):
        return [p[2] for p in self.props
                if p[0] == "set_property" and p[1] == "stream-record"]

    @staticmethod
    def _parse_icy(title):
        if " - " in title:
            a, t = title.split(" - ", 1)
            return a.strip() or None, t.strip() or None
        return None, title.strip() or None


class TestSession(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        for target, kw in [
            (mock.patch.object(recorder.config, "load",
                               return_value={"recordings_dir": str(self.root)}), {}),
            (mock.patch.object(recorder.notify, "notify"), {}),
            (mock.patch.object(recorder, "_finalize", return_value=None), {}),
        ]:
            target.start()
            self.addCleanup(target.stop)
        recorder._session = None  # isolate tests

    def _start(self, mode="full", icy="Kraftwerk - Autobahn"):
        self.fake = FakeMpv(icy=icy)
        p = mock.patch.object(recorder, "_mpv", return_value=self.fake)
        p.start()
        self.addCleanup(p.stop)
        return recorder.start(mode, {"name": "KEXP 90.3", "id": "kexp"})

    def test_start_requires_playback(self):
        self.fake = FakeMpv(playing=False)
        with mock.patch.object(recorder, "_mpv", return_value=self.fake):
            resp = recorder.start("full", {"name": "X"})
        self.assertFalse(resp["ok"])
        self.assertIn("nothing playing", resp["error"])

    def test_start_rejects_bad_mode(self):
        resp = recorder.start("shuffle", {"name": "X"})
        self.assertFalse(resp["ok"])

    def test_start_sets_stream_record_and_status(self):
        resp = self._start()
        self.assertTrue(resp["ok"])
        vals = self.fake.stream_record_values()
        self.assertEqual(len(vals), 1)
        self.assertTrue(vals[0].startswith(str(self.root / ".incoming")))
        st = recorder.status()
        self.assertTrue(st["active"])
        self.assertEqual(st["mode"], "full")
        self.assertEqual(st["station"], "KEXP 90.3")

    def test_double_start_refused(self):
        self._start()
        resp = recorder.start("full", {"name": "KEXP 90.3"})
        self.assertFalse(resp["ok"])
        self.assertIn("already recording", resp["error"])

    def test_full_mode_track_change_only_logs(self):
        self._start(mode="full")
        recorder.on_track_change("Neu!", "Hallogallo")
        self.assertEqual(len(self.fake.stream_record_values()), 1)  # no rotation
        self.assertEqual(len(recorder._session["tracklist"]), 2)  # start icy + change

    def test_track_mode_rotates_and_finalizes_previous(self):
        self._start(mode="track")
        recorder.on_track_change("Neu!", "Hallogallo")
        recorder._join_finalizers()
        vals = self.fake.stream_record_values()
        self.assertEqual(len(vals), 2)
        self.assertNotEqual(vals[0], vals[1])
        recorder._finalize.assert_called_once()
        args = recorder._finalize.call_args[0]
        self.assertEqual(args[3], "Kraftwerk - Autobahn")  # stem = track that ENDED
        self.assertTrue(recorder._finalize.call_args[1]["partial"])  # first file partial

    def test_stop_clears_property_and_state(self):
        self._start(mode="full")
        resp = recorder.stop()
        recorder._join_finalizers()
        self.assertTrue(resp["ok"])
        self.assertEqual(self.fake.stream_record_values()[-1], "")
        self.assertFalse(recorder.status()["active"])

    def test_stop_when_idle_errors(self):
        resp = recorder.stop()
        self.assertFalse(resp["ok"])

    def test_full_mode_stop_writes_tracklist_sidecar(self):
        self._start(mode="full")
        recorder.on_track_change("Neu!", "Hallogallo")
        with mock.patch.object(recorder, "_finalize",
                               return_value=self.root / "KEXP 90.3" / "s.m4a") as fin:
            (self.root / "KEXP 90.3").mkdir(parents=True, exist_ok=True)
            recorder.stop()
            recorder._join_finalizers()
        sidecar = self.root / "KEXP 90.3" / "s.tracklist.txt"
        self.assertTrue(sidecar.exists())
        self.assertIn("Kraftwerk - Autobahn", sidecar.read_text())
        self.assertIn("Hallogallo", sidecar.read_text())


if __name__ == "__main__":
    unittest.main()
