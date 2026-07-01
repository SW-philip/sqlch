"""Shared UI styling and custom CSS loading utilities."""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

def load_custom_css():
    """Load and inject dynamically computed CSS using the parsed runtime palette."""
    colors = palette.load()
    
    css = f"""
    window {{
        background: transparent;
        padding: 4px 18px 18px 4px;
    }}
    box.popup-window {{
        background-color: {colors['HALL']};
        color: {colors['SCORE']};
        border: 3px solid {colors['WING']};
        border-radius: 12px;
        box-shadow: 10px 10px 0 rgba(0,0,0,0.75);
    }}
    .sidebar {{
        background-color: {colors['STAGE']};
        border-right: 1px solid {colors['WING']};
        padding: 6px;
    }}
    .nav-btn {{
        padding: 10px;
        margin: 2px 0px;
        border-radius: 6px;
        color: {colors['REST']};
        background: transparent;
        border: none;
    }}
    .nav-btn:hover {{
        background-color: {colors['WING']};
        color: {colors['SCORE']};
    }}
    .nav-btn.active {{
        background-color: {colors['ROOT']};
        color: {colors['HALL']};
        font-weight: bold;
        box-shadow: 3px 3px 0 rgba(0,0,0,0.5);
    }}
    .card {{
        background-color: {colors['STAGE']};
        border: 2px solid {colors['WING']};
        border-radius: 8px;
        padding: 12px;
        box-shadow: 4px 4px 0 rgba(0,0,0,0.55);
    }}
    .station-row {{
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 2px;
    }}
    .station-row:hover {{
        background-color: {colors['WING']};
    }}
    .station-row.active {{
        background-color: {colors['SEVENTH']};
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
        border: 2px solid rgba(0,0,0,0.3);
        box-shadow: 3px 3px 0 rgba(0,0,0,0.6);
    }}
    .control-btn:hover {{
        background-color: {colors['MUTE']};
        box-shadow: 4px 4px 0 rgba(0,0,0,0.65);
    }}
    .control-btn:active {{
        box-shadow: 1px 1px 0 rgba(0,0,0,0.6);
    }}
    .vol-slider scale contents trough highlight {{
        background-color: {colors['ROOT']};
        border-radius: 3px;
    }}
    .vol-slider scale contents trough {{
        background-color: {colors['WING']};
        border-radius: 3px;
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
        box-shadow: 2px 2px 0 rgba(0,0,0,0.5);
    }}
    """
    
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )