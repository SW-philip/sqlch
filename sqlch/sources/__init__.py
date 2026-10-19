"""Media source registry. Each source module is listed explicitly (no
filesystem scan) and imported defensively so one broken source cannot take
down the others."""

import importlib
import logging

log = logging.getLogger(__name__)

RESERVED = ("library", "discover", "np")
_MODULES = ("local", "video", "jellyfin", "youtube", "spotify")


def source_config(name: str) -> dict:
    from sqlch.core import config
    return (config.load().get("sources") or {}).get(name) or {}


def safe_available(source) -> bool:
    """A source whose available() raises counts as unavailable."""
    try:
        return bool(source.available())
    except Exception:
        log.exception("source %s: available() failed", getattr(source, "NAME", source))
        return False


BROWSE = {"id": "browse", "title": "BROWSE"}
FAVORITES = {"id": "favorites", "title": "FAVORITES"}


def sections_for(source) -> list[dict]:
    """The source's own sections (BROWSE when it has none), then FAVORITES."""
    own = getattr(source, "sections", None)
    mine = [BROWSE]
    if own:
        try:
            mine = list(own())
        except Exception:
            log.exception("source %s: sections() failed", getattr(source, "NAME", source))
    return mine + [FAVORITES]


def _load(names=_MODULES, package=__name__) -> dict:
    registry = {}
    for n in names:
        try:
            mod = importlib.import_module(f"{package}.{n}")
            name = mod.NAME
        except Exception:
            log.exception("source %s failed to load", n)
            continue
        if name in RESERVED or name in registry:
            log.error("source %s: name %r is reserved or duplicated", n, name)
            continue
        registry[name] = mod
    return registry


# Last: source modules import source_config from this package while loading.
REGISTRY = _load()
