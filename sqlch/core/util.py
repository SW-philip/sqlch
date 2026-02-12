# ------------------------------------------------------------
# Lazy cache resolution (Nix-safe)
# ------------------------------------------------------------

_CACHE_DIR = None

def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import os
        from pathlib import Path
        base = os.environ.get("XDG_CACHE_HOME")
        if not base:
            base = str(Path.home() / ".cache")
        p = Path(base) / "sqlch"
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR

import re
from pathlib import Path

def normalize(name: str) -> str:
    return re.sub('[^a-z0-9]', '', name.lower())

def find_by_id(items, target):
    t = (target or '').strip().lower()
    for item in items:
        if str(item.get('id', '')).lower() == t:
            return item
        if str(item.get('name', '')).lower() == t:
            return item
    return None

def app_data_dir() -> Path:
    d = Path.home() / '.local/share/sqlch'
    d.mkdir(parents=True, exist_ok=True)
    return d