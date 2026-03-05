import json
import os
from pathlib import Path

from sqlch.core.paths import config_dir

APP_NAME = 'sqlch'


def config_path() -> Path:
    return config_dir() / 'sqlch.json'


def load() -> dict:
    p = config_path()
    if not p.exists():
        data = {'stations': [], 'channels': [], 'last_played': {}}
        p.write_text(json.dumps(data, indent=2))
        return data
    try:
        return json.loads(p.read_text())
    except Exception:
        return {'stations': [], 'channels': [], 'last_played': {}}


def save(data: dict):
    config_path().write_text(json.dumps(data, indent=2))
