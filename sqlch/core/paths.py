from pathlib import Path
import os

def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        p = Path(base) / "sqlch"
    else:
        p = Path.home() / ".cache" / "sqlch"
    p.mkdir(parents=True, exist_ok=True)
    return p
