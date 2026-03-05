from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Dict

import requests

from sqlch.core.paths import cache_dir


def _last_search_path() -> Path:
    return cache_dir() / "last_search.json"


def _base_url() -> str:
    return os.environ.get(
        "SQLCH_RADIOBROWSER_BASE", "https://de1.api.radio-browser.info/json"
    )


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------

def search(query: str, limit: int = 10) -> List[Dict]:
    params = {
        "name": query,
        "limit": limit,
        "hidebroken": "true",
        "order": "votes",
        "reverse": "true",
    }
    r = requests.get(f"{_base_url()}/stations/search", params=params, timeout=8)
    r.raise_for_status()

    results: List[Dict] = []
    for st in r.json():
        results.append(
            {
                "name": st.get("name"),
                "url": st.get("url_resolved"),
                "tags": st.get("tags"),
                "country": st.get("country"),
                "codec": st.get("codec"),
                "bitrate": st.get("bitrate"),
            }
        )
    return results


def save_last_search(results: List[Dict]) -> None:
    path = _last_search_path()
    path.write_text(json.dumps(results, indent=2))


def load_last_search() -> List[Dict]:
    path = _last_search_path()
    try:
        return json.loads(path.read_text())
    except Exception:
        return []
