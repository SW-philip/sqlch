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
    # Foreground text role: flips light/dark with the palette, unlike the
    # ink outline which stays dark. Text must never use the ink directly or
    # it vanishes on dark themes.
    score = colors.get('SCORE', '#121214')
    # Soft, deep drop shadows mimicking overlapping layers of craft board
    staff = colors.get('STAFF', '20,20,24')
    shadow = f"rgba({staff}, 0.85)"

    # LittleBigPlanet hem kit: every plate is "sewn" — a folded-over band of
    # its own fabric (semi-transparent so the fiber weave shows through),
    # a dashed thread stitched mid-hem, and light/shade insets that puff the
    # center. All derived from STAFF/white alphas so palette swaps need no
    # per-theme logic.
    hem_c = f"rgba({staff}, 0.14)"            # folded-fabric band
    shade_c = f"rgba({staff}, 0.25)"          # puff shade (bottom)
    lite_c = "rgba(255,255,255,0.40)"         # puff light catch (top)
    thread = f"rgba({staff}, 0.55)"           # stitch on light fills
    thread_light = "rgba(255,255,255,0.60)"   # stitch on dark fills

    # Inner pieces are stitched to the sheet, not floating: no ink outline,
    # just a slight soft contact shadow that deepens on lift and compresses
    # on press. Only the window frame (and popovers) truly float.
    slight = f"0 2px 3px rgba({staff}, 0.30)"
    slight_lift = f"0 3px 4px rgba({staff}, 0.35)"
    slight_press = f"0 1px 2px rgba({staff}, 0.25)"

    def hem(w: int, puff: bool = True) -> str:
        layers = [f"inset 0 0 0 {w}px {hem_c}"]
        if puff:
            layers += [
                f"inset 0 {w + 2}px 6px -{w}px {lite_c}",
                f"inset 0 -{w + 2}px 6px -{w}px {shade_c}",
            ]
        return ", ".join(layers)

    # REVISED FILTER: Uses independent organic noise grids layered as multipliers.
    # This prevents the lighting-clipping bug causing the blinding white mask in image_886f80.jpg.
    svg_tactile_filter = (
        "url(\"data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
        "<filter id='craft-texture'>"
        "  <!-- Fine textile thread weave mapping -->"
        "  <feTurbulence type='fractalNoise' baseFrequency='0.55' numOctaves='3' result='noise1'/>"
        "  <feColorMatrix type='matrix' values='0 0 0 0 0   0 0 0 0 0   0 0 0 0 0  0 0 0 0.10 0' in='noise1' result='fiber1'/>"
        "  <!-- Coarser recycled pulp clumps -->"
        "  <feTurbulence type='turbulence' baseFrequency='0.08' numOctaves='2' result='noise2'/>"
        "  <feColorMatrix type='matrix' values='0 0 0 0 0   0 0 0 0 0   0 0 0 0 0  0 0 0 0.08 0' in='noise2' result='fiber2'/>"
        "  <feBlend mode='multiply' in='SourceGraphic' in2='fiber1' result='blend1'/>"
        "  <feBlend mode='multiply' in='blend1' in2='fiber2'/>"
        "</filter>"
        "<rect width='100%25' height='100%25' filter='url(%23craft-texture)' fill='transparent'/>"
        "</svg>\")"
    )

    css = f"""
    window {{
        background-color: transparent;
    }}

    /* Main Popup Frame - Hand-cut backing sheet using targeted fallback hexes */
    .popup-window {{
        background-color: {colors.get('GRAD_HALL_LO', '#cebfa5')};
        background-image: {svg_tactile_filter}, linear-gradient(165deg, {colors.get('GRAD_HALL_HI', '#e6dfce')}, {colors.get('GRAD_HALL_LO', '#cebfa5')});
        background-repeat: repeat, no-repeat;
        color: {score};
        border: 4px solid {outline};
        border-radius: 16px;
        box-shadow: 8px 8px 0 0 {outline}, 14px 14px 0 0 {shadow}, {hem(8)};
        outline: 2px dashed {thread};
        outline-offset: -8px;
        margin: 4px 20px 20px 4px;
        padding: 4px;
    }}

    /* Navigation Sidebar - Suspended felt ribbon tab layout */
    .sidebar {{
        background-color: {colors.get('GRAD_STAGE_LO', '#b04343')};
        background-image: {svg_tactile_filter}, linear-gradient(130deg, {colors.get('GRAD_STAGE_HI', '#d35f5f')}, {colors.get('GRAD_STAGE_LO', '#b04343')});
        background-repeat: repeat, no-repeat;
        border-radius: 12px;
        padding: 5px 3px;
        box-shadow: {slight}, {hem(5)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
    }}

    /* Flat Vector Buttons with Tactile Bounce Responses */
    .nav-btn {{
        padding: 8px;
        margin: 3px 0px;
        border-radius: 8px;
        color: {colors.get('REST', '#4e4e52')};
        background: transparent;
        border: 3px solid transparent;
        transition: transform 80ms ease;
    }}
    .nav-btn:hover {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        transform: scale(1.05) translateY(-1px);
        box-shadow: {slight_lift}, {hem(3)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
    }}
    .nav-btn.active {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('ROOT', '#f4b84b')};
        color: {outline};
        font-weight: 900;
        box-shadow: {slight}, {hem(3)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
        transform: scale(1.1);
    }}

    /* Content Display Panels - explicit background assignments prevent default-theme transparency leakage */
    .card {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 14px;
        padding: 10px;
        box-shadow: {slight}, {hem(6)};
        outline: 2px dashed {thread};
        outline-offset: -5px;
        margin-bottom: 3px;
    }}

    /* Cover Art Holder - Looks like a stitched-on denim patch */
    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 12px;
        min-width: 124px;
        min-height: 124px;
        box-shadow: {slight}, {hem(5)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
        transform: rotate(-3deg);
    }}
    .cover-glyph {{
        font-size: 58px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}

    /* Backing plate for scrolling lists - a rounded, stitched fabric sheet
       the row patches are sewn onto */
    .list-plate {{
        background-color: {colors.get('HALL', '#fdf8ee')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 14px;
        padding: 6px;
        box-shadow: {slight}, {hem(4)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
    }}
    .list-plate row {{
        background: transparent;
    }}

    /* Structural Subheadings */
    .list-header {{
        background-color: {colors.get('WING', '#eaddca')};
        color: {score};
        text-shadow: 0 1px 0 {lite_c};
        font-weight: bold;
        border-radius: 10px;
        padding: 6px 10px;
        margin-bottom: 6px;
        box-shadow: {slight}, {hem(4)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
    }}

    /* Interactive Rows - resting state is already a sewn fabric strip;
       hover puffs it up and lifts it off the backing sheet */
    .station-row {{
        padding: 7px 10px;
        border-radius: 10px;
        margin-bottom: 2px;
        background-color: {colors.get('STAGE', '#f9f6f0')};
        box-shadow: {slight}, {hem(3, puff=False)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
    }}
    .station-row:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        box-shadow: {slight_lift}, {hem(3)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
        transform: translateY(-1px);
    }}
    .station-row.active {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('SEVENTH', '#79a383')};
        color: {colors.get('HALL', '#fdf8ee')};
        box-shadow: {slight}, {hem(3)};
        outline: 2px dashed {thread_light};
        outline-offset: -4px;
    }}
    .station-row.active label {{
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 1px 0 rgba({staff}, 0.60);
    }}
    .station-freq {{
        color: {colors.get('PIANO', '#2c2c30')};
        font-weight: 900;
        font-family: "Courier New", monospace;
        text-shadow: 0 1px 0 {lite_c};
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
        color: {score};
        box-shadow: {slight}, {hem(4)};
        outline: 2px dashed {thread};
        outline-offset: -4px;
    }}
    .control-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translateY(-1px);
        box-shadow: {slight_lift}, {hem(4)};
    }}
    .control-btn:active {{
        transform: translateY(2px);
        box-shadow: {slight_press}, {hem(4, puff=False)};
    }}
    .control-btn.primary {{
        min-width: 56px;
        min-height: 56px;
        border-radius: 20px;
        background-color: {colors.get('PIANO', '#2c2c30')};
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 1px 0 rgba({staff}, 0.60);
        outline: 2px dashed {thread_light};
    }}
    .control-btn.primary:hover {{
        background-color: {colors.get('SOTTO', '#454549')};
    }}

    /* Typography Overrides for Bubble-Pop Craft Themes */
    .meta-title {{
        font-family: "Fredoka", "Baloo 2", "Chalkboard SE", sans-serif;
        font-size: 1.25em;
        font-weight: 900;
        color: {score};
        text-shadow: 0 1px 0 {lite_c};
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
        color: {score};
        text-shadow: 0 1px 0 {lite_c};
        padding: 3px 8px;
        border-radius: 6px;
        box-shadow: {slight_press}, {hem(2, puff=False)};
        outline: 1px dashed {thread};
        outline-offset: -3px;
    }}
    .tag-chip:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translateY(-1px);
    }}

    /* Popover Context Overrides - Cardboard cutout with stitch details */
    popover.context-menu > contents {{
        background-color: {colors.get('GRAD_STAGE_LO', '#ece6da')};
        background-image: {svg_tactile_filter}, linear-gradient(160deg, {colors.get('GRAD_STAGE_HI', '#fbf9f5')}, {colors.get('GRAD_STAGE_LO', '#ece6da')});
        color: {score};
        border: 3px solid {outline};
        border-radius: 14px;
        box-shadow: 8px 8px 0 0 {shadow}, {hem(6)};
        outline: 2px dashed {thread};
        outline-offset: -6px;
        padding: 10px;
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
        border-radius: 8px;
        padding: 6px;
        box-shadow: {slight_press}, {hem(2, puff=False)};
        outline: 1px dashed {thread};
        outline-offset: -3px;
    }}
    .context-menu entry:focus-within {{
        outline: 2px dashed {colors.get('ROOT', '#f4b84b')};
        outline-offset: -3px;
    }}
    .context-menu separator {{
        background-color: rgba({staff}, 0.35);
        min-height: 2px;
        margin: 6px 0;
    }}

    .menu-btn {{
        padding: 5px 8px;
        border-radius: 8px;
        color: {score};
        background-color: {colors.get('WING', '#fff5dd')};
        box-shadow: {slight}, {hem(3)};
        outline: 2px dashed {thread};
        outline-offset: -3px;
    }}
    .menu-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translateY(-1px);
        box-shadow: {slight_lift}, {hem(3)};
    }}
    .menu-btn:active {{
        transform: translateY(1px);
        box-shadow: {slight_press}, {hem(3, puff=False)};
    }}
    .menu-btn.destructive-action {{
        color: {colors.get('FORTE', '#8c3b3b')};
        outline-color: {colors.get('FORTE', '#8c3b3b')};
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
