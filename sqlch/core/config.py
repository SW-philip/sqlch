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
from pathlib import Path
import json
import os
APP_NAME = 'sqlch'

def config_dir() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')
    return Path(base) / APP_NAME

def config_path() -> Path:
    return config_dir() / 'sqlch.json'

def ensure_exists():
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = config_path()
    if not p.exists():
        p.write_text(json.dumps({'stations': [], 'channels': [], 'last_played': {}}, indent=2))

def load() -> dict:
    ensure_exists()
    try:
        return json.loads(config_path().read_text())
    except Exception:
        return {'stations': [], 'channels': [], 'last_played': {}}

def save(data: dict):
    ensure_exists()
    config_path().write_text(json.dumps(data, indent=2))