from pathlib import Path
import os


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    p = Path(base) / "sqlch" if base else Path.home() / ".cache" / "sqlch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    p = Path(base) / "sqlch" if base else Path.home() / ".local" / "share" / "sqlch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    p = Path(base) / "sqlch" if base else Path.home() / ".config" / "sqlch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    p = Path(base) / "sqlch"
    p.mkdir(parents=True, exist_ok=True)
    return p
