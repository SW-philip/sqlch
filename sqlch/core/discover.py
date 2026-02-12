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
import requests
import json
import os
from pathlib import Path
from typing import List, Dict
XDG_CACHE_HOME = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
LAST_SEARCH = CACHE_DIR / 'last_search.json'
BASE = 'https://de1.api.radio-browser.info/json'

def search(query: str, limit: int=10):
    params = {'name': query, 'limit': limit, 'hidebroken': 'true', 'order': 'votes', 'reverse': 'true'}
    r = requests.get(f'{BASE}/stations/search', params=params, timeout=8)
    r.raise_for_status()
    results = []
    for st in r.json():
        results.append({'name': st.get('name'), 'url': st.get('url_resolved'), 'tags': st.get('tags'), 'country': st.get('country'), 'codec': st.get('codec'), 'bitrate': st.get('bitrate')})
    return results

def save_last_search(results: List[Dict]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_SEARCH.write_text(json.dumps(results, indent=2))

def load_last_search() -> List[Dict]:
    try:
        return json.loads(LAST_SEARCH.read_text())
    except Exception:
        return []