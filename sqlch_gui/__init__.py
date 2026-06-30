"""sqlch_gui — GTK4 graphical frontend for the sqlch radio daemon."""

import os
from pathlib import Path

VERSION = "1.0.0"

XDG_RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
XDG_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

CONTROL_SOCK = XDG_RUNTIME / "sqlch" / "control.sock"
MPV_SOCK = XDG_RUNTIME / "sqlch" / "mpv.sock"
CACHE_DIR = XDG_CACHE / "sqlch"
COVERS_DIR = CACHE_DIR / "covers"
LOGOS_DIR = CACHE_DIR / "logos"
ENRICHED_JSON = CACHE_DIR / "enriched.json"
LIBRARY_JSON = XDG_DATA / "sqlch" / "library.json"
FREQ_CACHE_JSON = XDG_DATA / "sqlch" / "freq_cache.json"