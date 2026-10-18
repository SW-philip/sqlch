"""Directory-tree browsing shared by the file-backed sources (local, video)."""

import os
import re
from pathlib import Path, PurePosixPath

from sqlch.sources.base import make_item

COVER_STEMS = ("cover", "folder", "front", "album")
COVER_EXT = (".jpg", ".jpeg", ".png")
SEARCH_LIMIT = 200


# No resolve(): symlinked album folders must keep working.
def safe(root: Path, rel: str | None) -> Path:
    if not rel:
        return root
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("path outside library")
    return root / rel


def title_from(stem: str) -> str:
    return re.sub(r"^\d+\s*[-._)]*\s*", "", stem) or stem


def _cover(directory: Path, cache: dict) -> str | None:
    if directory not in cache:
        names = {c.name.lower(): c for c in directory.iterdir() if c.is_file()}
        cache[directory] = next(
            (str(names[s + e]) for s in COVER_STEMS for e in COVER_EXT
             if s + e in names), None)
    return cache[directory]


class FileTree:
    def __init__(self, name: str, root_fn, exts: set, kind: str):
        self.name, self.root_fn, self.exts, self.kind = name, root_fn, exts, kind

    def matches(self, f: Path) -> bool:
        return f.suffix.lower() in self.exts

    def item(self, root: Path, f: Path, covers: dict) -> dict:
        rel = f.relative_to(root)
        parts = rel.parts[:-1]
        return make_item(
            self.name, rel.as_posix(), title_from(f.stem), kind=self.kind,
            artist=parts[-2] if len(parts) >= 2 else None,
            album=parts[-1] if parts else None,
            art=_cover(f.parent, covers))

    def available(self) -> bool:
        return self.root_fn().is_dir()

    def browse(self, path: str | None = None) -> list[dict]:
        root = self.root_fn()
        base = safe(root, path)
        entries = [e for e in base.iterdir() if not e.name.startswith(".")]
        key = lambda e: e.name.lower()  # noqa: E731
        dirs = sorted((e for e in entries if e.is_dir()), key=key)
        files = sorted((e for e in entries if e.is_file() and self.matches(e)), key=key)
        covers: dict = {}
        items = []
        for d in dirs:
            rel = d.relative_to(root).as_posix()
            items.append(make_item(self.name, rel, d.name, kind="folder", path=rel))
        items.extend(self.item(root, f, covers) for f in files)
        return items

    def search(self, query: str) -> list[dict]:
        words = (query or "").lower().split()
        if not words:
            return []
        root = self.root_fn()
        covers: dict = {}
        hits: list[dict] = []
        seen: set = set()
        try:
            st = os.stat(root)
            seen.add((st.st_dev, st.st_ino))
        except OSError:
            return hits
        for dirpath, dirs, files in os.walk(root, followlinks=True):
            keep = []
            for d in sorted(d for d in dirs if not d.startswith(".")):
                try:
                    st = os.stat(os.path.join(dirpath, d))
                except OSError:
                    continue
                ident = (st.st_dev, st.st_ino)
                if ident not in seen:
                    seen.add(ident)
                    keep.append(d)
            dirs[:] = keep
            for name in sorted(files):
                f = Path(dirpath) / name
                if name.startswith(".") or not self.matches(f):
                    continue
                rel = f.relative_to(root).as_posix().lower()
                if all(w in rel for w in words):
                    hits.append(self.item(root, f, covers))
                    if len(hits) >= SEARCH_LIMIT:
                        return hits
        return hits

    def file_for(self, item: dict) -> tuple[Path, dict]:
        root = self.root_fn()
        f = safe(root, item["id"])
        if not f.is_file():
            raise FileNotFoundError(str(f))
        if not self.matches(f):
            raise ValueError(f"not a {self.kind} file")
        it = self.item(root, f, {})
        return f, {k: it[k] for k in ("title", "artist", "album", "art")}
