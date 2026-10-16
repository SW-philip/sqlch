import contextlib
import io
import os
import unittest

from sqlch_gui.ui import trace


class TestTrace(unittest.TestCase):
    @unittest.skipIf(os.environ.get("SQLCH_GUI_TRACE") == "1", "tracing enabled")
    def test_off_by_default_writes_nothing(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            trace.trace("hello %s", "x", caller=True)
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
