import os
from pathlib import Path


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
    p.mkdir(mode=0o700, parents=True, exist_ok=True)
    # /tmp fallback: the dir may pre-exist (or be planted) with looser modes
    if p.stat().st_uid != os.getuid():
        raise PermissionError(f"{p} is owned by another user")
    os.chmod(p, 0o700)
    return p


def write_private(path: Path, text: str) -> None:
    """Atomically write a 0600 file (tokens, credentials)."""
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)
