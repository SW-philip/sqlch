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
import time
import json
import requests
from pathlib import Path
from typing import Dict, Any
from sqlch.core import spoti

def _cache_file() -> Path:
    return _cache_dir() / "enriched.json"

def _now() -> int:
    return int(time.time())

def _norm(s: str) -> str:
    return ' '.join(s.lower().strip().split())

def _cache_key(artist: str, track: str) -> str:
    return f'{_norm(artist)}::{_norm(track)}'

def _empty_result(artist: str, track: str) -> Dict[str, Any]:
    return {'artist': artist, 'track': track, 'album': None, 'year': None, 'cover': None, 'genres': [], 'source': 'unknown', 'ts': _now()}

def _load_cache() -> Dict[str, Any]:
    try:
        return json.loads(_cache_file.read_text())
    except Exception:
        return {}

def _save_cache(db: Dict[str, Any]) -> None:
    _cache_file.write_text(json.dumps(db, indent=2))

def _enrich_musicbrainz(artist: str, track: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    try:
        r = requests.get('https://musicbrainz.org/ws/2/recording/', params={'query': f'artist:"{artist}" AND recording:"{track}"', 'fmt': 'json', 'limit': 1}, headers={'User-Agent': 'sqlch/1.0'}, timeout=8)
        r.raise_for_status()
        data = r.json()
        recs = data.get('recordings') or []
        if not recs:
            return result
        rec = recs[0]
        releases = rec.get('releases') or []
        if releases:
            rel = releases[0]
            result['album'] = rel.get('title')
            if rel.get('date'):
                result['year'] = rel['date'].split('-')[0]
        result['source'] = 'musicbrainz'
    except Exception:
        pass
    return result

def enrich_track(artist: str, track: str) -> Dict[str, Any]:
    """
    Enrich track metadata using:
      1. Local enriched cache
      2. Spotify backend (spoti.py)
      3. MusicBrainz fallback
    """
    db = _load_cache()
    key = _cache_key(artist, track)
    if key in db:
        cached = db[key]
        cached['source'] = 'cache'
        return cached
    base = _empty_result(artist, track)
    sp = spoti.enrich(artist, track)
    if sp:
        base.update({'artist': sp['artist'], 'track': sp['track'], 'album': sp.get('album'), 'year': sp.get('year'), 'cover': sp.get('art_url'), 'genres': sp.get('genres', []), 'source': 'spotify'})
    else:
        mb = _enrich_musicbrainz(artist, track)
        for k, v in mb.items():
            if v is not None:
                base[k] = v
    base['ts'] = _now()
    db[key] = base
    _save_cache(db)
    return base
