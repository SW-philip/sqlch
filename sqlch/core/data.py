from sqlch.core.config import load, save
from sqlch.core.util import find_by_id, normalize

def get_stations():
    return load().get("stations", [])

def get_channels():
    return load().get("channels", [])

def add_station(name, url, category="Misc"):
    data = load()
    data.setdefault("stations", []).append({
        "name": name,
        "id": normalize(name),
        "category": category,
        "url": url
    })
    save(data)

def record_last_played(item, play_type):
    data = load()
    data["last_played"] = {
        "type": play_type,
        "id": item.get("id"),
        "name": item.get("name")
    }
    save(data)

def last_played():
    return load().get("last_played", {})
