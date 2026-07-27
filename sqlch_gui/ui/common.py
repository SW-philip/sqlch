"""Shared UI styling and custom CSS loading utilities with a Paper-Craft & Fabric Vibe."""

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

_css_provider: Gtk.CssProvider | None = None

def _hex_to_rgb(hex_val: str) -> str:
    """Convert a '#rrggbb' (or '#rgb') string into a bare 'r, g, b' triple for rgba() strings."""
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r}, {g}, {b}"

def load_custom_css():
    global _css_provider
    colors = palette.load()

    outline = colors.get('SHADOW', '#121214')
    score = colors.get('SCORE', '#121214')
    score_rgb = _hex_to_rgb(score)
    staff = colors.get('STAFF', '20,20,24')
    shadow = f"rgba({staff}, 0.85)"
    bg_color = colors.get('GRAD_HALL_LO', '#cebfa5')

    lite_c = "rgba(255,255,255,0.40)"

    slight = f"0 2px 3px rgba({staff}, 0.30)"
    slight_lift = f"0 3px 4px rgba({staff}, 0.35)"
    slight_press = f"0 1px 2px rgba({staff}, 0.25)"

    def cutout(dx: int, dy: int) -> str:
        """Hard-edged offset duplicate; pair with `border: Npx solid {outline}`."""
        return f"{dx}px {dy}px 0 0 {outline}"

    svg_tactile_filter = (
        "url(\"data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
        "<filter id='craft-texture'>"
        "  <feTurbulence type='fractalNoise' baseFrequency='0.55' numOctaves='3' result='noise1'/>"
        "  <feColorMatrix type='matrix' values='0 0 0 0 0   0 0 0 0 0   0 0 0 0 0  0 0 0 0.10 0' in='noise1' result='fiber1'/>"
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

    .popup-window {{
        background-color: {bg_color};
        background-image: {svg_tactile_filter}, linear-gradient(165deg, {colors.get('GRAD_HALL_HI', '#e6dfce')}, {bg_color});
        background-repeat: repeat, no-repeat;
        color: {score};
        border-radius: 13px;
        border: 2px solid {outline};
        box-shadow: 6px 6px 0 3px {outline}, 10px 10px 0 3px {shadow};
        margin: 2px 10px 10px 2px;
        padding: 2px;
    }}

    .nav-btn {{
        padding: 4px;
        margin: 2px 0px;
        border-radius: 6px;
        color: {colors.get('REST', '#4e4e52')};
        background: transparent;
        border: 2px solid transparent;
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
    .nav-btn:hover {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        transform: scale(1.05) translateY(-1px);
        border: 2px solid {outline};
        box-shadow: {cutout(2, 2)}, {slight_lift};
    }}
    .nav-btn.active {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('ROOT', '#f4b84b')};
        color: {outline};
        font-weight: 900;
        border: 2px solid {outline};
        box-shadow: {cutout(2, 2)}, {slight};
        transform: scale(1.1);
    }}

    .card {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 10px;
        padding: 4px;
        border: 2px solid {outline};
        box-shadow: {cutout(4, 4)}, {slight};
        margin-bottom: 2px;
    }}

    .cover-art {{
        background-color: {colors.get('WING', '#e2dacf')};
        border-radius: 10px;
        min-width: 98px;
        min-height: 98px;
        box-shadow: {slight};
    }}
    .cover-glyph {{
        font-size: 38px;
        font-weight: 900;
        color: {colors.get('PIANO', '#2c2c30')};
        text-shadow: 0 2px 0 {lite_c};
        transform: rotate(-6deg);
    }}

    .corner-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.6em;
        padding: 2px 5px;
        border-radius: 8px;
        border: 2px solid {outline};
        box-shadow: {cutout(2, 2)};
        margin: 5px;
        text-shadow: 0 -1px 0 rgba(255,255,255,0.35), 0 1px 1px rgba({staff},0.5);
    }}
    .corner-tag-left {{
        background-color: {colors.get('ROOT', '#f4b84b')};
        color: {outline};
        transform: rotate(-4deg);
    }}
    .corner-tag-right {{
        background-color: {colors.get('BAR', '#6a6a6a')};
        color: {score};
        transform: rotate(4deg);
    }}
    .corner-tag-rec {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        color: {colors.get('BAR', '#6b6b70')};
        transform: rotate(-4deg);
    }}
    .corner-tag-rec.active {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
    }}

    .list-plate {{
        background-color: {colors.get('HALL', '#fdf8ee')};
        background-image: {svg_tactile_filter};
        background-repeat: repeat;
        border-radius: 12px;
        padding: 5px;
        border: 2px solid {outline};
        box-shadow: {cutout(4, 4)}, {slight};
    }}
    .list-plate row {{
        background: transparent;
    }}

    .list-header {{
        background-color: {colors.get('WING', '#eaddca')};
        color: {score};
        font-weight: bold;
        border-radius: 8px;
        padding: 5px 8px;
        margin-bottom: 5px;
        border: 2px solid {outline};
        box-shadow: {cutout(3, 3)}, {slight};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.40), 0 1px 1px rgba({staff},0.5);
    }}

    .station-row {{
        padding: 4px 6px;
        border-radius: 8px;
        margin-bottom: 2px;
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border: 2px solid {outline};
        box-shadow: {cutout(2, 2)}, {slight};
    }}
    .station-row:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        border: 2px solid {outline};
        box-shadow: {cutout(3, 3)}, {slight_lift};
        transform: translateY(-1px);
    }}
    .station-row.active {{
        background-image: {svg_tactile_filter};
        background-color: {colors.get('SEVENTH', '#79a383')};
        color: {colors.get('HALL', '#fdf8ee')};
        border: 2px solid {colors.get('ROOT', '#f4b84b')};
        box-shadow: {cutout(2, 2)}, {slight};
    }}
    .station-row.active label {{
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.30), 0 1px 2px rgba({staff}, 0.80);
    }}
    .station-freq {{
        color: {colors.get('PIANO', '#2c2c30')};
        font-weight: 900;
        font-family: "Courier New", monospace;
        text-shadow: 0 1px 0 {lite_c};
    }}
    .station-row.active .station-freq {{
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.20), 0 1px 1px rgba({staff}, 0.70);
    }}
    .station-live {{
        font-size: 0.8em;
        font-style: italic;
        color: {colors.get('FIFTH', '#6b6b70')};
        text-shadow: 0 1px 0 {lite_c};
    }}
    .station-row.active .station-live {{
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: none;
    }}

    .control-btn {{
        border-radius: 11px;
        min-width: 28px;
        min-height: 28px;
        padding: 0;
        background-color: {colors.get('WING', '#f2ece1')};
        color: {score};
        box-shadow: {slight};
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
    .control-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        box-shadow: 0 0 0 1px {outline}, {slight_lift};
        transform: translateY(-1px);
    }}
    .control-btn:active {{
        transform: translateY(2px);
        box-shadow: {slight_press};
    }}
    .control-btn.primary {{
        min-width: 36px;
        min-height: 36px;
        border-radius: 13px;
        background-color: {colors.get('PIANO', '#2c2c30')};
        color: {colors.get('HALL', '#fdf8ee')};
        box-shadow: 0 0 0 2px {outline}, {slight};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.30), 0 1px 2px rgba({staff}, 0.70);
    }}
    .control-btn.primary:hover {{
        background-color: {colors.get('SOTTO', '#454549')};
        box-shadow: 0 0 0 2px {outline}, {slight_lift};
    }}

    .meta-title {{
        font-family: "Fredoka", "Baloo 2", "Chalkboard SE", sans-serif;
        font-size: 1.05em;
        font-weight: 900;
        color: {score};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.45), 0 1px 1px rgba({staff},0.6), 1px 3px 0 {outline};
    }}
    .meta-artist {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.88em;
        color: {colors.get('FORTE', '#8c3b3b')};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.35), 0 1px 1px rgba({staff},0.4), 1px 2px 0 {outline};
    }}
    .meta-genre {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.85em;
        color: {colors.get('BAR', '#6b6b70')};
        font-style: italic;
        text-shadow: 0 1px 0 {lite_c};
    }}

    .thread-label {{
        font-family: "Fredoka", sans-serif;
        font-size: 0.75em;
        font-style: italic;
        color: rgba({score_rgb}, 0.28);
        text-shadow: 0 1px 0 {lite_c};
    }}
    .thread-label.lit {{
        color: {colors.get('ROOT', '#f4b84b')};
        font-weight: 700;
    }}

    .tech-badge, .tag-chip {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.72em;
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        padding: 2px 6px;
        border-radius: 6px;
        border: 1px solid {outline};
        box-shadow: {cutout(1, 1)}, {slight_press};
        text-shadow: 0 -1px 0 rgba(255,255,255,0.40), 0 1px 1px rgba({staff},0.4);
    }}
    .tag-chip:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        transform: translateY(-1px);
        border: 1px solid {outline};
        box-shadow: {cutout(2, 2)}, {slight_lift};
    }}
    .tech-badge.rec-badge {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        text-shadow: 0 1px 0 rgba({staff}, 0.60);
        outline: 1px solid {outline};
    }}

    .small-badge {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.65em;
        background-color: {colors.get('MUTE', '#e5dcce')};
        color: {colors.get('BAR', '#6b6b70')};
        padding: 2px 6px;
        border-radius: 5px;
        text-shadow: 0 1px 0 {lite_c};
    }}

    .ribbon-label {{
        font-weight: 900;
        font-size: 0.7em;
        letter-spacing: 0.08em;
        color: {outline};
        text-shadow: 0 1px 0 rgba(255,255,255,0.25);
    }}

    .pennant-label {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.7em;
        color: {outline};
        text-shadow: 0 1px 0 rgba(255,255,255,0.25);
    }}

    .pennant-btn {{
        background: transparent;
        border: none;
        box-shadow: none;
        padding: 0;
        transition: transform 80ms ease;
    }}
    .pennant-btn:hover {{
        background: transparent;
        transform: translateY(-1px);
    }}
    .pennant-btn:active {{
        transform: translateY(1px);
    }}

    .knob-tag {{
        font-family: "Courier New", monospace;
        font-weight: 900;
        font-size: 0.58em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.05em;
        text-shadow: 0 1px 0 {lite_c};
    }}

    .readout-line {{
        font-family: "Courier New", monospace;
        font-size: 0.72em;
        color: {colors.get('BAR', '#6b6b70')};
        letter-spacing: 0.02em;
        text-shadow: 0 1px 0 {lite_c};
    }}

    .brand-tag {{
        font-family: "Courier New", monospace;
        font-weight: 700;
        font-size: 0.56em;
        letter-spacing: 0.08em;
        color: rgba({score_rgb}, 0.35);
        text-shadow: 0 1px 0 {lite_c};
        margin: 6px 8px;
    }}

    popover.context-menu > contents {{
        background-color: {colors.get('GRAD_STAGE_LO', '#ece6da')};
        background-image: {svg_tactile_filter}, linear-gradient(160deg, {colors.get('GRAD_STAGE_HI', '#fbf9f5')}, {colors.get('GRAD_STAGE_LO', '#ece6da')});
        color: {score};
        border-radius: 14px;
        border: 2px solid {outline};
        box-shadow: 8px 8px 0 3px {shadow};
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
        text-shadow: 0 1px 0 {lite_c};
    }}
    .context-menu entry {{
        background-color: {colors.get('WING', '#fff5dd')};
        border-radius: 8px;
        padding: 6px;
        border: 1px solid {outline};
        box-shadow: {cutout(1, 1)}, {slight_press};
    }}
    .context-menu entry:focus-within {{
        border: 1px solid {colors.get('ROOT', '#f4b84b')};
        box-shadow: 0 0 0 2px {colors.get('ROOT', '#f4b84b')};
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
        border: 2px solid {outline};
        box-shadow: {cutout(3, 3)}, {slight};
        transition: transform 80ms ease, box-shadow 80ms ease;
    }}
    .menu-btn:hover {{
        background-color: {colors.get('MUTE', '#e5dcce')};
        border: 2px solid {outline};
        box-shadow: {cutout(4, 4)}, {slight_lift};
        transform: translateY(-1px);
    }}
    .menu-btn:active {{
        transform: translateY(1px);
        box-shadow: {cutout(2, 2)}, {slight_press};
    }}
    .menu-btn.destructive-action {{
        color: {colors.get('FORTE', '#8c3b3b')};
        border-color: {colors.get('FORTE', '#8c3b3b')};
    }}
    .menu-btn.destructive-action:hover {{
        background-color: {colors.get('FORTE', '#8c3b3b')};
        color: {colors.get('HALL', '#fdf8ee')};
        border-color: transparent;
    }}

    .field-entry {{
        background-color: {colors.get('WING', '#fff5dd')};
        color: {score};
        border-radius: 8px;
        padding: 4px 8px;
        border: 2px solid {outline};
        box-shadow: {cutout(2, 2)}, {slight_press};
    }}
    .field-entry:focus-within {{
        border: 2px solid {colors.get('ROOT', '#f4b84b')};
        box-shadow: 0 0 0 2px {colors.get('ROOT', '#f4b84b')};
    }}

    /* Album Deck Outer Container - baseline rotation state */
    .album-deck-wrapper {{
        border-radius: 12px;
        transition: transform 250ms cubic-bezier(0.4, 0.0, 0.2, 1);
        transform: rotate(-3deg);
    }}

    /* Subtle geometric physics push when flipped open */
    .album-deck-wrapper.flipped {{
        transform: rotate(2deg) scale(1.02);
    }}

    /* Back side styling - Looks like a typewriter ledger scrap pasted to cardboard */
    .art-card-back {{
        background-color: {colors.get('STAGE', '#f9f6f0')};
        border-radius: 12px;
        border: 2px solid {outline};
        box-shadow: inset 0 0 4px rgba({staff}, 0.15), {cutout(3, 3)}, {slight};
        padding: 6px;
    }}

    /* Track info container styling */
    .tracklist-container label {{
        font-family: "Courier New", monospace;
        font-size: 0.72em;
        font-weight: bold;
        color: {colors.get('PIANO', '#2c2c30')};
        padding: 2px;
        text-shadow: 0 1px 0 {lite_c};
    }}

    /* Flip corner glyph - a small clickable tag tucked into the art's own
       bottom-right corner, same rotation family as corner-tag-right
       (used by the top-right format tag) since both sit on the right. */
    .corner-tag-flip {{
        background-color: {colors.get('BAR', '#6a6a6a')};
        color: {score};
        border: 2px solid {outline};
        border-radius: 8px;
        padding: 3px 5px;
        min-height: 0;
        min-width: 0;
        margin: 5px;
        box-shadow: {cutout(2, 2)};
        transform: rotate(4deg);
        transition: transform 120ms ease, background-color 120ms ease;
    }}
    .corner-tag-flip:hover {{
        background-color: {colors.get('WING', '#fff5dd')};
        transform: rotate(4deg) scale(1.1);
    }}
    .corner-tag-flip:active {{
        transform: rotate(4deg) scale(0.92);
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
