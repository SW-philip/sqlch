from pathlib import Path

from sqlch.sources import source_config
from sqlch.sources._files import FileTree
from sqlch.sources.base import Target

NAME = "local"
TITLE = "LOCAL"
LABEL = "Local Library"
HINT = ('Set "sources": {"local": {"library_root": "/path/to/music"}} '
        "in ~/.config/sqlch/sqlch.json")

AUDIO_EXT = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wav", ".wma"}


def _root() -> Path:
    cfg = source_config(NAME)
    root = cfg.get("library_root") if isinstance(cfg, dict) else None
    return Path(root if isinstance(root, str) and root else "~/Music").expanduser()


_tree = FileTree(NAME, lambda: _root(), AUDIO_EXT, "track")
available = _tree.available
browse = _tree.browse
search = _tree.search


def resolve(item: dict) -> Target:
    f, meta = _tree.file_for(item)
    return Target(str(f), False, meta)
