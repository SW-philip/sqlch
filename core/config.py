from pathlib import Path
import json
import os

APP_NAME = "sqlch"

def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(base) / APP_NAME

def config_path() -> Path:
    return config_dir() / "sqlch.json"

def ensure_exists():
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = config_path()

    if not p.exists():
        p.write_text(json.dumps({
            "stations": [],
            "channels": [],
            "last_played": {}
        }, indent=2))

def load() -> dict:
    ensure_exists()
    try:
        return json.loads(config_path().read_text())
    except Exception:
        return {"stations": [], "channels": [], "last_played": {}}

def save(data: dict):
    ensure_exists()
    config_path().write_text(json.dumps(data, indent=2))
