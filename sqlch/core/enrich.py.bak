import os
import time
import json
import base64
import requests
import configparser
from pathlib import Path
from typing import Dict, Any, Optional

# -----------------------------
# Paths / cache
# -----------------------------

CACHE_DIR = Path.home() / ".cache/sqlch"
CACHE_FILE = CACHE_DIR / "enriched.json"
TOKEN_CACHE = CACHE_DIR / "spotify_token.json"
CONF = Path.home() / ".config/sqlch/spotify.conf"


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Utilities
# -----------------------------

def _now() -> int:
    return int(time.time())


def _empty_result(artist: str, track: str) -> Dict[str, Any]:
    return {
        "artist": artist,
        "track": track,
        "album": None,
        "year": None,
        "cover": None,
        "genres": [],
        "source": "unknown",
        "ts": _now(),
    }


def _load_cache() -> Dict[str, Any]:
    _ensure_cahce_dir()
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(db: Dict[str, Any]) -> None:
    _ensure_cache_dir()
    CACHE_FILE.write_text(json.dumps(db, indent=2))


# -----------------------------
# Spotify helpers
# -----------------------------

def _load_spotify_creds() -> Optional[tuple[str, str]]:
    cid = os.getenv("SPOTIFY_CLIENT_ID")
    csec = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not cid or not csec:
        return None

    return cid, csec

def _get_spotify_token() -> Optional[str]:
    _ensure_cache_dir()
    if TOKEN_CACHE.exists():
        try:
            tok = json.loads(TOKEN_CACHE.read_text())
            if tok.get("expires_at", 0) > time.time():
                return tok["access_token"]
        except Exception:
            pass

    creds = _load_spotify_creds()
    if not creds:
        return None

    cid, csec = creds
    auth = base64.b64encode(f"{cid}:{csec}".encode()).decode()

    try:
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {auth}"},
            data={"grant_type": "client_credentials"},
            timeout=8,
        )
        resp.raise_for_status()
        tok = resp.json()

        tok["expires_at"] = time.time() + tok["expires_in"] - 30
        TOKEN_CACHE.write_text(json.dumps(tok))
        return tok["access_token"]
    except Exception:
        return None

def _spotify_artist_genres(artist_id: str, token: str) -> list[str]:
    try:
        r = requests.get(
            f"https://api.spotify.com/v1/artists/{artist_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=6,
        ).json()
        return r.get("genres", [])
    except Exception:
        return []

# -----------------------------
# Enrichment engines
# -----------------------------

def _enrich_musicbrainz(artist: str, track: str) -> Dict[str, Any]:
    result = {}

    try:
        r = requests.get(
            "https://musicbrainz.org/ws/2/recording/",
            params={
                "query": f'artist:"{artist}" AND recording:"{track}"',
                "fmt": "json",
                "limit": 1,
            },
            headers={"User-Agent": "sqlch/1.0"},
            timeout=8,
        ).json()

        recs = r.get("recordings") or []
        if not recs:
            return result

        rec = recs[0]
        releases = rec.get("releases") or []

        if releases:
            rel = releases[0]
            result["album"] = rel.get("title")
            if rel.get("date"):
                result["year"] = rel["date"].split("-")[0]

        result["source"] = "musicbrainz"
    except Exception:
        pass

    return result


def _enrich_spotify(artist: str, track: str) -> Dict[str, Any]:
    token = _get_spotify_token()
    if not token:
        return {}

    result = {}

    try:
        r = requests.get(
            "https://api.spotify.com/v1/search",
            params={"q": f"{artist} {track}", "type": "track", "limit": 1},
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        ).json()

        items = r.get("tracks", {}).get("items") or []
        if not items:
            return result

        item = items[0]
        album = item.get("album", {})

        result["album"] = album.get("name")
        if album.get("release_date"):
            result["year"] = album["release_date"].split("-")[0]

        images = album.get("images") or []
        if images:
            result["cover"] = images[0]["url"]

        artists = item.get("artists") or []
        if artists:
            aid = artists[0].get("id")
            if aid:
                result["genres"] = _spotify_artist_genres(aid, token)

        result["source"] = "spotify"
    except Exception:
        pass

    return result

# -----------------------------
# Public API
# -----------------------------

def enrich_track(artist: str, track: str) -> Dict[str, Any]:
    key = f"{artist} - {track}"

    db = _load_cache()
    if key in db:
        cached = db[key]
        cached["source"] = "cache"
        return cached

    base = _empty_result(artist, track)

    # MusicBrainz first (free, fast, no auth)
    mb = _enrich_musicbrainz(artist, track)
    base.update({k: v for k, v in mb.items() if v is not None})

    # Spotify second (richer data)
    sp = _enrich_spotify(artist, track)
    base.update({k: v for k, v in sp.items() if v is not None})

    base["ts"] = _now()

    db[key] = base
    _save_cache(db)

    return base

