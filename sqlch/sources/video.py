from pathlib import Path

from sqlch.sources import source_config
from sqlch.sources._files import FileTree
from sqlch.sources.base import Target

NAME = "video"
TITLE = "VIDEO"
LABEL = "Local Video"
HINT = ('Set "sources": {"video": {"library_root": "/path/to/videos"}} '
        "in ~/.config/sqlch/sqlch.json")

VIDEO_EXT = {".mkv", ".mp4", ".webm", ".avi", ".mov", ".m4v", ".ts"}


def _root() -> Path:
    cfg = source_config(NAME)
    root = cfg.get("library_root") if isinstance(cfg, dict) else None
    return Path(root if isinstance(root, str) and root else "~/Videos").expanduser()


_tree = FileTree(NAME, lambda: _root(), VIDEO_EXT, "video")
available = _tree.available
browse = _tree.browse
search = _tree.search


def resolve(item: dict) -> Target:
    f, meta = _tree.file_for(item)
    return Target(str(f), True, meta)
