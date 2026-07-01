"""Shared UI styling and custom CSS loading utilities."""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

_css_provider: Gtk.CssProvider | None = None

def load_custom_css():
    global _css_provider
    colors = palette.load()

    outline = colors['SCORE']
    shadow  = "rgba(0,0,0,0.9)"

    css = f"""
    window {{
        background-color: transparent;
    }}
    box.popup-window {{
        background-color: {colors['HALL']};
        color: {colors['SCORE']};
        border: 3px solid {outline};
        border-radius: 10px;
        box-shadow: 10px 10px 0 {shadow};
        margin: 4px 18px 18px 4px;
    }}
    .sidebar {{
        background-color: {colors['STAGE']};
        border: 3px solid {outline};
        border-radius: 10px;
        padding: 6px;
        box-shadow: 6px 6px 0 {shadow};
        margin-right: 4px;
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
        box-shadow: 2px 2px 0 {shadow};
    }}
    .nav-btn.active {{
        background-color: {colors['ROOT']};
        color: {colors['HALL']};
        font-weight: bold;
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 {shadow};
    }}
    .card {{
        background-color: {colors['STAGE']};
        border: 2px solid {outline};
        border-radius: 8px;
        padding: 12px;
        box-shadow: 5px 5px 0 {shadow};
    }}
    .cover-art {{
        background-color: {colors['WING']};
        border: 2px solid {outline};
        border-radius: 6px;
        min-width: 80px;
        min-height: 80px;
        box-shadow: 3px 3px 0 {shadow};
    }}
    .list-header {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
        font-weight: bold;
        border: 2px solid {outline};
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 12px;
        box-shadow: 3px 3px 0 {shadow};
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
        box-shadow: 2px 2px 0 {shadow};
    }}
    .station-row.active {{
        background-color: {colors['SEVENTH']};
        color: {colors['HALL']};
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 {shadow};
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
        box-shadow: 5px 5px 0 {shadow};
    }}
    .control-btn:active {{
        transform: translate(3px, 3px);
        box-shadow: 1px 1px 0 {shadow};
    }}
    .vol-slider scale trough highlight {{
        background-color: {colors['ROOT']};
        border-radius: 3px;
    }}
    .vol-slider scale trough {{
        background-color: {colors['WING']};
        border-radius: 3px;
        border: 1px solid {outline};
    }}
    .meta-title {{
        font-size: 1.1em;
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
        color: {colors['FIFTH']};
        background-color: {colors['WING']};
        padding: 2px 6px;
        border-radius: 4px;
        border: 1px solid {outline};
        box-shadow: 2px 2px 0 {shadow};
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
