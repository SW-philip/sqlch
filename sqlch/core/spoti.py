import base64
import json
import os
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Dict, Any

import requests

from sqlch.core.paths import cache_dir

CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


def _track_cache() -> Path:
    return cache_dir() / 'spotify_tracks.json'


def _artist_cache() -> Path:
    return cache_dir() / 'spotify_artists.json'


def _token_cache() -> Path:
    return cache_dir() / 'spotify_token.json'


def _spotify_base() -> str:
    return os.environ.get("SQLCH_SPOTIFY_BASE", "https://api.spotify.com/v1")


def _spotify_auth_base() -> str:
    return os.environ.get("SQLCH_SPOTIFY_AUTH_BASE", "https://accounts.spotify.com")


def _now() -> int:
    return int(time.time())


def _norm(s: str) -> str:
    return ' '.join(s.lower().strip().split())


def _key(artist: str, track: str) -> str:
    return f'{_norm(artist)}::{_norm(track)}'


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2))


def _get_token() -> Optional[str]:
    if _token_cache().exists():
        try:
            tok = json.loads(_token_cache().read_text())
            if tok.get('expires_at', 0) > time.time():
                return tok['access_token']
        except Exception:
            pass
    cid = os.getenv('SPOTIFY_CLIENT_ID')
    sec = os.getenv('SPOTIFY_CLIENT_SECRET')
    if not cid or not sec:
        return None
    auth = base64.b64encode(f'{cid}:{sec}'.encode()).decode()
    r = requests.post(
        f'{_spotify_auth_base()}/api/token',
        headers={'Authorization': f'Basic {auth}'},
        data={'grant_type': 'client_credentials'},
        timeout=8,
    )
    r.raise_for_status()
    tok = r.json()
    tok['expires_at'] = time.time() + tok['expires_in'] - 30
    _token_cache().write_text(json.dumps(tok))
    return tok['access_token']


def _search_track(artist: str, track: str, token: str) -> Optional[dict]:
    q = f'artist:"{artist}" track:"{track}"'
    r = requests.get(
        f'{_spotify_base()}/search',
        headers={'Authorization': f'Bearer {token}'},
        params={'q': q, 'type': 'track', 'limit': 3},
        timeout=8,
    )
    r.raise_for_status()
    items = r.json().get('tracks', {}).get('items') or []
    if not items:
        return None
    for item in items:
        sp_artist = item['artists'][0]['name']
        sp_track = item['name']
        if _similar(sp_artist, artist) >= 0.85 and _similar(sp_track, track) >= 0.75:
            return item
    return None


def _artist_genres(artist_id: str, token: str) -> list[str]:
    cache_path = _artist_cache()
    cache = _load_json(cache_path)

    if artist_id in cache:
        return cache[artist_id].get('genres', [])

    r = requests.get(
        f'{_spotify_base()}/artists/{artist_id}',
        headers={'Authorization': f'Bearer {token}'},
        timeout=8,
    )
    r.raise_for_status()

    genres = r.json().get('genres', [])
    cache[artist_id] = {'genres': genres, 'ts': _now()}
    _save_json(cache_path, cache)
    return genres


def enrich(artist: str, track: str) -> Optional[Dict[str, Any]]:
    """
    Cache-first Spotify enrichment.

    Returns canonical enriched metadata or None if no confident match.
    """
    cache = _load_json(_track_cache())
    k = _key(artist, track)
    if k in cache:
        entry = cache[k]
        if (_now() - entry.get('cached_at', 0)) < CACHE_TTL:
            return entry
    token = _get_token()
    if not token:
        return None
    item = _search_track(artist, track, token)
    if not item:
        return None
    album = item['album']
    primary_artist = item['artists'][0]
    enriched = {
        'artist':       primary_artist['name'],
        'track':        item['name'],
        'album':        album['name'],
        'album_artist': album['artists'][0]['name'],
        'year':         album['release_date'][:4],
        'genres':       _artist_genres(primary_artist['id'], token),
        'art_url':      album['images'][0]['url'] if album['images'] else None,
        'spotify_id':   item['id'],
        'artist_id':    primary_artist['id'],
        'isrc':         item.get('external_ids', {}).get('isrc'),
        'source':       'spotify',
        'cached_at':    _now(),
    }
    cache[k] = enriched
    _save_json(_track_cache(), cache)
    return enriched
