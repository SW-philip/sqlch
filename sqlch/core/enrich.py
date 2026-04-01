from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from sqlch.core import spoti
from sqlch.core.paths import cache_dir


# How long before a cached result is considered stale (30 days)
CACHE_TTL = 60 * 60 * 24 * 30

# Fields that represent "quality" — more filled = better result
_QUALITY_FIELDS = ('album', 'year', 'cover', 'genres', 'isrc')


def _cache_file() -> Path:
    return cache_dir() / "enriched.json"


def _now() -> int:
    return int(time.time())


def _norm(s: str) -> str:
    return ' '.join(s.lower().strip().split())


def _cache_key(artist: str, track: str) -> str:
    return f'{_norm(artist)}::{_norm(track)}'


def _empty_result(artist: str, track: str) -> dict[str, Any]:
    return {
        'artist': artist,
        'track': track,
        'album': None,
        'year': None,
        'cover': None,
        'genres': [],
        'source': 'unknown',
        'ts': _now(),
    }


def _quality_score(result: dict[str, Any]) -> int:
    """Count how many quality fields are populated."""
    score = 0
    for f in _QUALITY_FIELDS:
        v = result.get(f)
        if v:
            score += 1
    return score


def _is_stale(result: dict[str, Any]) -> bool:
    return (_now() - result.get('ts', 0)) > CACHE_TTL


def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(_cache_file().read_text())
    except Exception:
        return {}


def _save_cache(db: dict[str, Any]) -> None:
    _cache_file().write_text(json.dumps(db, indent=2))


def _enrich_musicbrainz(artist: str, track: str) -> dict[str, Any]:
    base = _mb_base_url()
    result: dict[str, Any] = {}
    try:
        r = requests.get(
            f'{base}/recording/',
            params={
                'query': f'artist:"{artist}" AND recording:"{track}"',
                'fmt': 'json',
                'limit': 1,
            },
            headers={'User-Agent': 'sqlch/1.0'},
            timeout=8,
        )
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

        genres = _mb_genres_for_recording(rec.get('id'))
        if genres:
            result['genres'] = genres

        result['source'] = 'musicbrainz'

    except Exception:
        pass

    return result


def _mb_base_url() -> str:
    return os.environ.get("SQLCH_MUSICBRAINZ_BASE", "https://musicbrainz.org/ws/2")


def _mb_genres_for_recording(recording_id: str | None) -> list:
    """Fetch MusicBrainz tags for a recording and return the top genre tags."""
    if not recording_id:
        return []
    try:
        base = _mb_base_url()
        r = requests.get(
            f'{base}/recording/{recording_id}',
            params={'fmt': 'json', 'inc': 'tags+genres'},
            headers={'User-Agent': 'sqlch/1.0'},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()

        # Sort by vote count descending, cap at 5
        genres_with_votes = [
            g for g in (data.get('genres') or data.get('tags') or [])
            if g.get('count', 0) > 0
        ]
        genres_with_votes.sort(key=lambda g: g.get('count', 0), reverse=True)
        return [g['name'] for g in genres_with_votes[:5]]

    except Exception:
        return []


def enrich_track(artist: str, track: str) -> dict[str, Any]:
    """
    Enrich track metadata using:
      1. Local enriched cache (skipped if stale)
      2. Spotify backend (spoti.py)
      3. MusicBrainz fallback

    Cache is refreshed when:
      - The entry is older than CACHE_TTL (30 days)
      - The fresh result has a higher quality score (more fields populated)
    """
    db = _load_cache()
    key = _cache_key(artist, track)
    cached = db.get(key)

    # Return cache hit if fresh
    if cached and not _is_stale(cached):
        cached['source'] = 'cache'
        return cached

    # Fetch fresh result
    base = _empty_result(artist, track)

    sp = spoti.enrich(artist, track)
    if sp:
        base.update({
            'artist':  sp['artist'],
            'track':   sp['track'],
            'album':   sp.get('album'),
            'year':    sp.get('year'),
            'cover':   sp.get('art_url'),
            'genres':  sp.get('genres', []),
            'source':  'spotify',
        })
    else:
        mb = _enrich_musicbrainz(artist, track)
        for k, v in mb.items():
            if v is not None:
                base[k] = v

    base['ts'] = _now()

    # Only overwrite cache if fresh result is at least as good
    if cached is None or _quality_score(base) >= _quality_score(cached):
        db[key] = base
        _save_cache(db)
    else:
        # Keep the richer cached result but reset its TTL so we don't keep retrying
        cached['ts'] = _now()
        db[key] = cached
        _save_cache(db)
        cached['source'] = 'cache'
        return cached

    return base
