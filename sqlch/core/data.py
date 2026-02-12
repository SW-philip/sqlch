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
from sqlch.core.config import load, save
from sqlch.core.util import find_by_id, normalize

def get_stations():
    return load().get('stations', [])

def get_channels():
    return load().get('channels', [])

def add_station(name, url, category='Misc'):
    data = load()
    data.setdefault('stations', []).append({'name': name, 'id': normalize(name), 'category': category, 'url': url})
    save(data)

def record_last_played(item, play_type):
    data = load()
    data['last_played'] = {'type': play_type, 'id': item.get('id'), 'name': item.get('name')}
    save(data)

def last_played():
    return load().get('last_played', {})