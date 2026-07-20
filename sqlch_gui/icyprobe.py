"""Re-export of the ICY prober, which now lives in sqlch.core so the
daemon can run it independent of whether the GUI is running."""

from sqlch.core.icyprobe import fetch_stream_title

__all__ = ["fetch_stream_title"]
