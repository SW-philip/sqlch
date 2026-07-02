"""Shared UI styling and custom CSS loading utilities with a Paper-Craft & Fabric Vibe."""

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

_css_provider: Gtk.CssProvider | None = None

def load_custom_css():
    global _css_provider
    colors = palette.load()

    # Thick, sharp cartoon outlines (Paper Mario) - SHADOW stays dark ink
    # regardless of theme brightness, unlike SCORE which is a foreground/
    # text role that flips light/dark depending on the palette.
    outline = colors.get('SHADOW', '#121214')
    # Soft, deep drop shadows mimicking overlapping layers of craft board
    shadow = f"rgba({colors.get('STAFF', '20,20,24')}, 0.85)"

    # REVISED FILTER: Uses independent organic noise grids layered as multipliers.
    # This prevents the lighting-clipping bug causing the blinding white mask in image_886f80.jpg.
    svg_tactile_filter = (
        "url(\"data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
        "<filter id='craft-texture'>"
        "  <!-- Fine textile thread weave mapping -->"
        "  <feTurbulence type='fractalNoise' baseFrequency='0.55' numOctaves='3' result='noise1'/>"
        "  <feColorMatrix type='matrix' values='0 0 0 0 0   0 0 0 0 0   0 0 0 0 0  0 0 0 0.05 0' in='noise1' result='fiber1'/>"
        "  <!-- Coarser recycled pulp clumps -->"
        "  <feTurbulence type='turbulence' baseFrequency='0.08' numOctaves='2' result='noise2'/>"
        "  <feColorMatrix type='matrix' values='0 0 0 0 0   0 0 0 0 0   0 0 0 0 0  0 0 0 0.04 0' in='noise2' result='fiber2'/>"
        "  <feBlend mode='multiply' in='SourceGraphic' in2='fiber1' result='blend1'/>"
        "  <feBlend mode='multiply' in='blend1' in2='fiber2'/>"
        "</filter>"
        "<rect width='100%25' height='100%25' filter='url(%23craft-texture)' fill='transparent'/>"
        "</svg>\")"
    )

    # Dashed border-style keyword to mimic sewing/stitching lines on felt layers
    stitch_style = "dashed"

    css = f"""
    window {{
        background-color: transparent;
    }}

    /* Main Popup Frame - Hand-cut backing sheet using targeted fallback hexes */
    .popup-window {{
        background-color: {colors.get('GRAD_HALL_LO', '#cebfa5')};
        background-image: {svg_tactile_filter}, linear-gradient(165deg, {colors.get('GRAD_HALL_HI', '#e6dfce')}, {colors.get('GRAD_HALL_LO', '#cebfa5')});
        background-repeat: repeat, no-repeat;
        color: {outline};
        border: 4px solid {outline};
        border-radius: 16px;
        box-shadow: 8px 8px 0 0 {outline}, 14px 14px 0 0 {shadow};
        margin: 6px 24px 24px 6px;
        padding: 4px;
    }}

    /* Navigation Sidebar - Suspended felt ribbon tab layout */
    .sidebar {{
        background-color: {colors.get('GRAD_STAGE_LO', '#b04343')};
        background-image: {svg_tactile_filter}, linear-gradient(130deg, {colors.get('GRAD_STAGE_HI', '#d35f5f')}, {colors.get('GRAD_STAGE_LO', '#b04343')});
        background-repeat: repeat, no-repeat;
        border: 2px solid {outline};
        border-style: {stitch_style};
        border-radius: 12px;
        padding: 8px 4px;
        box-shadow: 5px 5px 0 0 {outline};
        margin-left: -6px;
    }}

    /* Flat Vector Buttons with Tactile Bounce Responses */
    .nav-btn {{
        padding: 12px;
        margin: 4px 0px;
        border-radius: 8px;
        color: {colors.get('REST', '#4e4e52')};
        background: transparent;
        border: 3px solid transparent;
        transition: transform 80ms ease;
    }}
    .nav-btn:hover {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('WING', '#fff5dd')};
        color: {outline};
        border: 3px solid {outline};
        transform: scale(1.05) translate(-1px, -1px);
        box-shadow: 3px 3px 0 0 {outline};
    }}
    .nav-btn.active {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('ROOT', '#f4b84b')};
        color: {outline};
        font-weight: 900;
        border: 3px solid {outline};
        box-shadow: 4px 4px 0 0 {outline};
        transform: scale(1.1);
    }}

    /* Content Display Panels - explicit background assignments prevent default-theme transparency leakage */
    .card {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border: 3px solid {outline};
        border-radius: 14px;
        padding: 14px;
        box-shadow: 5px 5px 0 0 {outline};
        transform: rotate(0.8deg);
        margin-bottom: 8px;
    }}
    .card:nth-child(even) {{
        transform: rotate(-0.8deg);
    }}

    /* Cover Art Holder - Looks like a stitched-on denim patch */
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border: 2px solid {outline};
        border-style: {stitch_style};
        border-radius: 12px;
        min-width: 124px;
        min-height: 124px;
        box-shadow: 4px 4px 0 0 {outline};
        transform: rotate(-3deg);
    }}
    .cover-glyph {{
        font-size: 58px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        transform: rotate(-6deg);
    }}

    /* Structural Subheadings */
    .list-header {{
        background-color: {colors.get('WING', '#eaddca')};
        color: {outline};
        font-weight: bold;
        border: 3px solid {outline};
        border-radius: 10px;
        padding: 8px 12px;
        margin-bottom: 12px;
        box-shadow: 3px 3px 0 0 {outline};
    }}

    /* Interactive Rows */
    .station-row {{
        padding: 10px 14px;
        border-radius: 10px;
        margin-bottom: 4px;
        border: 3px solid transparent;
    }}
    .station-row:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        border: 3px solid {outline};
        box-shadow: 4px 4px 0 0 {outline};
        transform: translate(-1px, -1px);
    }}
    .station-row.active {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('SEVENTH', '#79a383')};
        color: {colors.get('HALL', '#fdf8ee')};
        border: 3px solid {outline};
        box-shadow: 4px 4px 0 0 {outline};
    }}
    .station-row.active label {{
        color: {colors.get('HALL', '#fdf8ee')};
    }}
    .station-freq {{
        color: {colors.get('PIANO', '#2c2c30')};
        font-weight: 900;
        font-family: "Courier New", monospace;
    }}
    .station-row.active .station-freq {{
        color: {colors.get('HALL', '#fdf8ee')};
    }}
    .station-live {{
        font-size: 0.8em;
        font-style: italic;
        color: {colors.get('FIFTH', '#6b6b70')};
    }}
    .station-row.active .station-live {{
        color: {colors.get('HALL', '#fdf8ee')};
    }}

    /* Playback Control Deck Circular Buttons - Chunky plastic/wooden token layout */
    .control-btn {{
        border-radius: 16px;
        min-width: 44px;
        min-height: 44px;
        padding: 0;
        background-color: {colors.get('WING', '#f2ece1')};
        color: {outline};
        border: 3px solid {outline};
        box-shadow: 4px 4px 0 0 {outline};
    }}
    .control-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translateY(-2px);
        box-shadow: 6px 6px 0 0 {outline};
    }}
    .control-btn:active {{
        transform: translate(4px, 4px);
        box-shadow: 0px 0px 0 0 transparent;
    }}
    .control-btn.primary {{
        min-width: 56px;
        min-height: 56px;
        border-radius: 20px;
        background-color: {colors.get('PIANO', '#2c2c30')};
        color: {colors.get('HALL', '#fdf8ee')};
    }}
    .control-btn.primary:hover {{
        background-color: {colors.get('SOTTO', '#454549')};
    }}

    /* Volume Sliders Tracker Track and Thumb elements */
    .vol-slider scale trough {{
        background-color: {colors.get('WING', '#e8e2d5')};
        border-radius: 8px;
        border: 3px solid {outline};
        min-height: 12px;
        margin: 6px 0;
    }}
    .vol-slider scale trough highlight {{
        background-color: {colors.get('ROOT', '#f4b84b')};
        border-radius: 6px;
    }}
    .vol-slider scale slider {{
        background-color: {colors.get('SCORE', '#121214')};
        border: 3px solid {outline};
        border-radius: 8px;
        min-width: 18px;
        min-height: 22px;
        box-shadow: 2px 2px 0 0 rgba(0,0,0,0.4);
    }}
    .vol-slider button {{
        color: {colors.get('REST', '#4e4e52')};
        min-width: 26px;
        min-height: 26px;
        border-radius: 8px;
    }}
    .vol-slider button:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        color: {outline};
    }}

    /* Typography Overrides for Bubble-Pop Craft Themes */
    .meta-title {{
        font-family: "Fredoka", "Baloo 2", "Chalkboard SE", sans-serif;
        font-size: 1.25em;
        font-weight: 900;
        color: {outline};
    }}
    .meta-artist {{
        font-family: "Fredoka", sans-serif;
        font-size: 1.0em;
        color: {colors.get('FORTE', '#8c3b3b')};
    }}
    .meta-genre {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.85em;
        color: {colors.get('BAR', '#6b6b70')};
        font-style: italic;
    }}

    /* Sticker Tags */
    .tech-badge, .tag-chip {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.8em;
        background-color: {colors.get('WING', '#fff5dd')};
        color: {outline};
        padding: 4px 10px;
        border-radius: 6px;
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 0 {outline};
        transform: rotate(-1deg);
    }}
    .tag-chip:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translate(-1px, -1px) rotate(-1deg);
    }}

    /* Popover Context Overrides - Cardboard cutout with stitch details */
    popover.context-menu > contents {{
        background-color: {colors.get('GRAD_STAGE_LO', '#ece6da')};
        background-image: {svg_tactile_filter}, linear-gradient(160deg, {colors.get('GRAD_STAGE_HI', '#fbf9f5')}, {colors.get('GRAD_STAGE_LO', '#ece6da')});
        color: {outline};
        border: 2px solid {outline};
        border-style: {stitch_style};
        border-radius: 14px;
        box-shadow: 8px 8px 0 0 {shadow};
        padding: 14px;
    }}
    popover.context-menu > arrow {{
        background-color: {colors.get('GRAD_STAGE_LO', '#ece6da')};
    }}
    .context-menu label {{
        color: {colors.get('REST', '#4e4e52')};
        font-size: 0.85em;
        font-weight: bold;
        margin-top: 4px;
    }}
    .context-menu entry {{
        background-color: {colors.get('WING', '#fff5dd')};
        border: 3px solid {outline};
        border-radius: 8px;
        padding: 6px;
    }}
    .context-menu entry:focus-within {{
        border: 3px solid {colors.get('ROOT', '#f4b84b')};
        box-shadow: 3px 3px 0 0 {outline};
    }}
    .context-menu separator {{
        background-color: {outline};
        min-height: 2px;
        margin: 6px 0;
    }}

    .menu-btn {{
        padding: 6px 10px;
        border-radius: 8px;
        color: {outline};
        background-color: {colors.get('WING', '#fff5dd')};
        border: 2px solid {outline};
        box-shadow: 3px 3px 0 0 {outline};
    }}
    .menu-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translate(-1px, -1px);
        box-shadow: 4px 4px 0 0 {outline};
    }}
    .menu-btn:active {{
        transform: translate(2px, 2px);
        box-shadow: 1px 1px 0 0 {outline};
    }}
    .menu-btn.destructive-action {{
        color: {colors.get('FORTE', '#8c3b3b')};
        border-color: {colors.get('FORTE', '#8c3b3b')};
    }}
    .menu-btn.destructive-action:hover {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
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
