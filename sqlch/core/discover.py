_CACHE_DIR = None

def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import os
        from pathlib import Path
        base = os.environ.get('XDG_CACHE_HOME')
        if not base:
            base = str(Path.home() / '.cache')
        p = Path(base) / 'sqlch'
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR

import json
import requests
from typing import List, Dict
from pathlib import Path

# keep your existing _cache_dir() but use it
def _last_search_path() -> Path:
    return _cache_dir() / "last_search.json"

BASE = "https://de1.api.radio-browser.info/json"

def save_last_search(results: List[Dict]):
    path = _last_search_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2))

def load_last_search() -> List[Dict]:
    path = _last_search_path()
    try:
        return json.loads(path.read_text())
    except Exception:
        return []
