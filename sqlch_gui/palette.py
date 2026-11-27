"""Palette loader: reads palette.sh and returns a color dict."""

import os
import re
from pathlib import Path

_DEFAULTS: dict[str, str] = {
    "NIGHT": "#232136",
    "DUSK": "#2a273f",
    "FADE": "#393552",
    "GLOAM": "#44415a",
    "HORIZON": "#6e6a86",
    "HAZE": "#908caa",
    "LIGHT": "#e0def4",
    "FLARE": "#eb6f92",
    "STAR": "#3e8fb0",
    "MOON": "#9ccfd8",
    "METEOR": "#ea9a97",
    "SUN": "#c4a7e7",
    "SPOT": "#f6c177",
    "UMBRA": "#0f0e17",
    "GRAD_NIGHT_HI": "#282544",
    "GRAD_NIGHT_LO": "#1a1828",
    "GRAD_DUSK_HI": "#302c4d",
    "GRAD_DUSK_LO": "#211f36",
    "GRAD_FADE_HI": "#443f60",
    "GRAD_FADE_LO": "#2d2944",
    "UMBRA_RGB": "15,14,23",
    "MURK": "#1a1828",
    "DAWN": "#c9c5da",
    "UMBRA_A_OUTER": "0.50",
    "UMBRA_A_DROP": "0.55",
    "UMBRA_A_HOVER": "0.65",
    "UMBRA_A_INSET_TOP": "0.08",
    "UMBRA_A_INSET_BOT": "0.30",
    "UMBRA_A_BORDER": "0.07",
    "HALO": "0 1px 2px rgba(0,0,0,0.80)",
    "ARC": "12px",
}


# Palettes written before hrzn's dusk rename still use these names.
LEGACY: dict[str, str] = {
    "HALL": "NIGHT", "DIM": "MURK", "STAGE": "DUSK", "MUTE": "GLOAM", "WING": "FADE",
    "SCORE": "LIGHT", "LYRIC": "DAWN", "REST": "HAZE",
    "ROOT": "SUN", "FIFTH": "MOON", "SEVENTH": "STAR", "SOTTO": "METEOR",
    "FORTE": "FLARE", "FERMATA": "AURORA", "PIANO": "SPOT", "TACET": "ECLIPSE",
    "BAR": "HORIZON", "LEDGER": "CORONA", "SHADOW": "UMBRA", "STAFF": "UMBRA_RGB",
    "TEMPO": "ARC", "MEASURE": "HALO", "ROOT_RGB": "SUN_RGB", "FORTE_RGB": "FLARE_RGB",
    "GRAD_HALL_HI": "GRAD_NIGHT_HI", "GRAD_HALL_LO": "GRAD_NIGHT_LO",
    "GRAD_STAGE_HI": "GRAD_DUSK_HI", "GRAD_STAGE_LO": "GRAD_DUSK_LO",
    "GRAD_WING_HI": "GRAD_FADE_HI", "GRAD_WING_LO": "GRAD_FADE_LO",
    **{f"STAFF_A_{s}": f"UMBRA_A_{s}" for s in ("OUTER", "DROP", "HOVER", "INSET_TOP", "INSET_BOT", "BORDER")},
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
                p[LEGACY.get(m.group(1), m.group(1))] = m.group(2)
    except Exception:
        pass
    return p