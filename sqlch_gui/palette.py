"""Palette loader: reads palette.sh and returns a color dict."""

import os
import re
from pathlib import Path

_DEFAULTS: dict[str, str] = {
    "HALL": "#232136",
    "STAGE": "#2a273f",
    "WING": "#393552",
    "MUTE": "#44415a",
    "BAR": "#6e6a86",
    "REST": "#908caa",
    "SCORE": "#e0def4",
    "FORTE": "#eb6f92",
    "SEVENTH": "#3e8fb0",
    "FIFTH": "#9ccfd8",
    "SOTTO": "#ea9a97",
    "ROOT": "#c4a7e7",
    "PIANO": "#f6c177",
    "SHADOW": "#0f0e17",
    "GRAD_HALL_HI": "#282544",
    "GRAD_HALL_LO": "#1a1828",
    "GRAD_STAGE_HI": "#302c4d",
    "GRAD_STAGE_LO": "#211f36",
    "STAFF": "15,14,23",
}


def palette_path() -> str:
    """The palette.sh path load() reads by default."""
    return os.environ.get(
        "SQLCH_GUI_PALETTE",
        str(Path.home() / ".config" / "waybar" / "palette.sh"),
    )


def load(path: str | None = None) -> dict[str, str]:
    """Parse a palette.sh file into a color dict. Falls back to Rosé Pine Moon."""
    p = dict(_DEFAULTS)
    if path is None:
        path = palette_path()
    try:
        for line in Path(path).read_text().splitlines():
            m = re.match(r'^export\s+(\w+)="([^"]*)"', line)
            if m:
                p[m.group(1)] = m.group(2)
    except Exception:
        pass
    return p