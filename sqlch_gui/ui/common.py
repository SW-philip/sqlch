"""Shared UI styling and custom CSS loading utilities."""

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

_css_provider: Gtk.CssProvider | None = None
_GRAIN_PATH = Path(__file__).resolve().parent.parent / "assets" / "paper_grain.png"

def load_custom_css():
    global _css_provider
    colors = palette.load()

    outline = colors['SCORE']
    shadow  = f"rgba({colors['STAFF']},0.9)"
    grain   = f"url('{_GRAIN_PATH.as_uri()}')"

    css = f"""
    window {{
        background-color: transparent;
    }}
    .popup-window {{
        background-image: {grain}, linear-gradient(160deg, {colors['GRAD_HALL_HI']}, {colors['GRAD_HALL_LO']});
        background-repeat: repeat, no-repeat;
        color: {colors['SCORE']};
        border: 3px solid {outline};
        border-radius: 10px;
        box-shadow: 10px 10px 0 {shadow};
        margin: 4px 18px 18px 4px;
    }}
    .sidebar {{
        background-image: {grain}, linear-gradient(160deg, {colors['GRAD_STAGE_HI']}, {colors['GRAD_STAGE_LO']});
        background-repeat: repeat, no-repeat;
        border: 2px solid {outline};
        border-radius: 10px;
        padding: 6px;
        box-shadow: 5px 5px 0 {shadow};
    }}
    .nav-btn {{
        padding: 10px;
        margin: 2px 0px;
        border-radius: 6px;
        color: {colors['REST']};
        background: transparent;
        border: 2px solid transparent;
    }}
    .nav-btn:hover {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 2px solid {outline};
        transform: translate(-1px, -1px);
        box-shadow: 4px 4px 0 {shadow};
    }}
    .nav-btn.active {{
        background-color: {colors['ROOT']};
        color: {colors['HALL']};
        font-weight: bold;
        border: 2px solid {outline};
        box-shadow: 5px 5px 0 {shadow};
    }}
    .card {{
        background-color: {colors['STAGE']};
        background-image: {grain};
        background-repeat: repeat;
        border: 2px solid {outline};
        border-radius: 8px;
        padding: 12px;
        box-shadow: 4px 4px 0 {shadow};
    }}
    .cover-art {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        border-radius: 6px;
        min-width: 120px;
        min-height: 120px;
        box-shadow: 4px 4px 0 {shadow};
        transform: rotate(-2deg);
    }}
    .cover-glyph {{
        font-size: 52px;
        font-weight: bold;
        color: {colors['PIANO']};
        transform: rotate(-8deg);
    }}
    .list-header {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        font-weight: bold;
        border: 2px solid {outline};
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 12px;
        box-shadow: 4px 4px 0 {shadow};
    }}
    .station-row {{
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 2px;
        border: 2px solid transparent;
    }}
    .station-row:hover {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        box-shadow: 4px 4px 0 {shadow};
    }}
    .station-row.active {{
        background-color: {colors['SEVENTH']};
        color: {colors['HALL']};
        border: 2px solid {outline};
        box-shadow: 4px 4px 0 {shadow};
    }}
    .station-row.active label {{
        color: {colors['HALL']};
    }}
    .station-freq {{
        color: {colors['PIANO']};
        font-weight: bold;
        font-family: monospace;
    }}
    .station-row.active .station-freq {{
        color: {colors['HALL']};
    }}
    .control-btn {{
        border-radius: 50%;
        min-width: 40px;
        min-height: 40px;
        padding: 0;
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 2px solid {outline};
        box-shadow: 4px 4px 0 {shadow};
    }}
    .control-btn:hover {{
        background-color: {colors['MUTE']};
        transform: translate(-1px, -1px);
        box-shadow: 6px 6px 0 {shadow};
    }}
    .control-btn:active {{
        transform: translate(3px, 3px);
        box-shadow: 1px 1px 0 {shadow};
    }}
    .control-btn.primary {{
        min-width: 52px;
        min-height: 52px;
        -gtk-icon-size: 22px;
        background-color: {colors['PIANO']};
        color: {colors['HALL']};
    }}
    .control-btn.primary:hover {{
        background-color: {colors['SOTTO']};
    }}
    .vol-slider scale trough {{
        background-color: {colors['WING']};
        border-radius: 5px;
        border: 2px solid {outline};
        min-height: 10px;
        margin: 6px 0;
    }}
    .vol-slider scale trough highlight {{
        background-color: {colors['ROOT']};
        border-radius: 5px;
        min-height: 10px;
    }}
    .vol-slider scale slider {{
        background-color: {colors['SCORE']};
        border: 2px solid {outline};
        border-radius: 50%;
        min-width: 16px;
        min-height: 16px;
        box-shadow: 3px 3px 0 {shadow};
    }}
    .vol-slider scale slider:hover {{
        background-color: {colors['MUTE']};
    }}
    .vol-slider scale slider:active {{
        box-shadow: 1px 1px 0 {shadow};
    }}
    .vol-slider button {{
        color: {colors['REST']};
        min-width: 28px;
        min-height: 28px;
        border-radius: 50%;
    }}
    .vol-slider button:hover {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
    }}
    .meta-title {{
        font-family: "Baloo 2", "Fredoka", sans-serif;
        font-size: 1.15em;
        font-weight: bold;
        color: {colors['SCORE']};
    }}
    .meta-artist {{
        font-size: 0.95em;
        color: {colors['FORTE']};
    }}
    .meta-genre {{
        font-size: 0.85em;
        color: {colors['BAR']};
        font-style: italic;
    }}
    .tech-badge {{
        font-family: monospace;
        font-size: 0.8em;
        font-weight: bold;
        color: {colors['FIFTH']};
        background-color: {colors['WING']};
        padding: 3px 8px;
        border-radius: 6px;
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 {shadow};
    }}
    .tag-chip {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 2px solid {outline};
        border-radius: 12px;
        padding: 4px 10px;
        font-size: 0.75em;
        box-shadow: 2px 2px 0 {shadow};
    }}
    .tag-chip:hover {{
        background-color: {colors['MUTE']};
    }}
    .station-live {{
        font-size: 0.8em;
        font-style: italic;
        color: {colors['FIFTH']};
    }}
    .station-row.active .station-live {{
        color: {colors['HALL']};
    }}
    popover.context-menu > contents {{
        background-image: linear-gradient(160deg, {colors['GRAD_STAGE_HI']}, {colors['GRAD_STAGE_LO']});
        color: {colors['SCORE']};
        border: 2px solid {outline};
        border-radius: 10px;
        box-shadow: 6px 6px 0 {shadow};
        padding: 12px;
    }}
    popover.context-menu > arrow {{
        background-color: {colors['GRAD_STAGE_LO']};
    }}
    .context-menu label {{
        color: {colors['REST']};
        font-size: 0.85em;
        font-weight: bold;
        margin-top: 4px;
    }}
    .context-menu entry {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        border: 2px solid {outline};
        border-radius: 6px;
        padding: 4px 8px;
    }}
    .context-menu entry:focus-within {{
        border: 2px solid {colors['ROOT']};
        box-shadow: 3px 3px 0 {shadow};
    }}
    .context-menu separator {{
        background-color: {outline};
        min-height: 2px;
        margin: 6px 0;
    }}
    .menu-btn {{
        padding: 6px 10px;
        border-radius: 6px;
        color: {colors['SCORE']};
        background-color: {colors['WING']};
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 {shadow};
    }}
    .menu-btn:hover {{
        background-color: {colors['MUTE']};
        transform: translate(-1px, -1px);
        box-shadow: 4px 4px 0 {shadow};
    }}
    .menu-btn:active {{
        transform: translate(2px, 2px);
        box-shadow: 1px 1px 0 {shadow};
    }}
    .menu-btn.destructive-action {{
        color: {colors['FORTE']};
        border-color: {colors['FORTE']};
    }}
    .menu-btn.destructive-action:hover {{
        background-color: {colors['FORTE']};
        color: {colors['HALL']};
    }}
    """

    display = Gdk.Display.get_default()
    if _css_provider is not None:
        Gtk.StyleContext.remove_provider_for_display(display, _css_provider)
    _css_provider = Gtk.CssProvider()
    _css_provider.load_from_string(css)
    Gtk.StyleContext.add_provider_for_display(
        display,
        _css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
