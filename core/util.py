import re
from pathlib import Path

def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())

def find_by_id(items, target):
    t = (target or "").strip().lower()
    for item in items:
        if str(item.get("id", "")).lower() == t:
            return item
        if str(item.get("name", "")).lower() == t:
            return item
    return None

def app_data_dir() -> Path:
    d = Path.home() / ".local/share/sqlch"
    d.mkdir(parents=True, exist_ok=True)
    return d
