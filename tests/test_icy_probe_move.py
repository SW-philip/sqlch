import unittest


class TestIcyProbeMove(unittest.TestCase):
    def test_core_module_has_fetch_stream_title(self):
        from sqlch.core.icyprobe import fetch_stream_title
        self.assertTrue(callable(fetch_stream_title))

    def test_gui_module_reexports_same_function(self):
        from sqlch.core.icyprobe import fetch_stream_title as core_fn
        from sqlch_gui.icyprobe import fetch_stream_title as gui_fn
        self.assertIs(core_fn, gui_fn)
