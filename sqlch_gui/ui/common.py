"""Shared UI styling: generates and installs the flat, swaync-style stylesheet."""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .. import palette

_css_provider: Gtk.CssProvider | None = None


def _hex_to_rgb(hex_val: str) -> str:
    """Convert '#rrggbb' (or '#rgb') into a bare 'r, g, b' triple for rgba() strings."""
    h = hex_val.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"{r}, {g}, {b}"


def _build_css(colors: dict) -> str:
    """Build the app stylesheet from a palette color dict. Pure — no display,
    no side effects. Mirrors the vocabulary of ~/.config/swaync/style.css:
    flat fills, a hairline border, one soft drop; the hard-offset shadow and
    the faint fiber-noise live only on the outer .popup-window shell."""
    outline = colors.get('SHADOW', '#0f0e17')
    score = colors.get('SCORE', '#e0def4')
    score_rgb = _hex_to_rgb(score)
    staff = colors.get('STAFF', '15, 14, 23')

    stage = colors.get('STAGE', '#2a273f')
    wing = colors.get('WING', '#393552')
    dim = colors.get('DIM', '#1a1828')
    hall = colors.get('HALL', '#232136')
    lyric = colors.get('LYRIC', '#c9c5da')
    rest = colors.get('REST', '#908caa')
    root = colors.get('ROOT', '#c4a7e7')
    seventh = colors.get('SEVENTH', '#3e8fb0')
    piano = colors.get('PIANO', '#f6c177')
    forte = colors.get('FORTE', '#eb6f92')
    sotto = colors.get('SOTTO', '#ea9a97')

    a_outer = colors.get('STAFF_A_OUTER', '0.50')
    a_drop = colors.get('STAFF_A_DROP', '0.55')
    a_inset = colors.get('STAFF_A_INSET_BOT', '0.30')

    mono = '"JetBrains Mono", "Courier New", monospace'
    prop = '"Inter", "system-ui", sans-serif'

    hairline = f"1px solid rgba({score_rgb}, 0.14)"
    rule = f"1px solid rgba({score_rgb}, 0.13)"
    drop = f"0 1px 1px rgba({staff}, {a_drop})"
    recess = f"inset 0 1px 2px rgba({staff}, {a_inset})"
    press = f"inset 0 1px 3px rgba({staff}, 0.6)"
    shell_shadow = f"3px 4px 0 0 rgba({staff}, {a_drop})"

    shell_noise = (
        "url(\"data:image/svg+xml;utf8,"
        "<svg xmlns='http://www.w3.org/2000/svg' width='90' height='90'>"
        "<filter id='craft'>"
        "<feTurbulence type='fractalNoise' baseFrequency='0.55' numOctaves='3' result='n'/>"
        "<feColorMatrix type='matrix' values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.06 0' in='n' result='fiber'/>"
        "<feBlend mode='multiply' in='SourceGraphic' in2='fiber'/>"
        "</filter>"
        "<rect width='100%25' height='100%25' filter='url(%23craft)' fill='transparent'/>"
        "</svg>\")"
    )

    return f"""
    window {{
        background-color: transparent;
        font-family: {mono};
        font-size: {colors.get('TEMPO', '12px')};
        color: {score};
    }}

    .popup-window {{
        background-color: {wing};
        background-image: {shell_noise};
        background-repeat: repeat;
        color: {score};
        font-family: {mono};
        border-radius: 18px;
        border: 1px solid rgba({score_rgb}, {a_outer});
        box-shadow: {shell_shadow};
        margin: 2px 10px 10px 2px;
        padding: 2px;
    }}

    .nav-row {{
        background-color: {stage};
        border-radius: 7px;
        padding: 3px 6px;
        border: {hairline};
        box-shadow: {drop};
    }}

    .nav-btn {{
        padding: 4px;
        margin: 2px 0;
        border-radius: 7px;
        color: {rest};
        background-color: {wing};
        background-image: none;
        border: {hairline};
        box-shadow: {drop};
    }}
    .nav-btn:hover {{
        background-color: {stage};
        color: {score};
    }}
    .nav-btn.active {{
        background-color: {root};
        color: {outline};
        font-weight: 700;
        box-shadow: {drop};
    }}

    .card {{
        background-color: {stage};
        border-radius: 12px;
        padding: 4px;
        border: {hairline};
        box-shadow: {drop};
        margin-bottom: 2px;
    }}

    .cover-art {{
        background-color: {wing};
        border-radius: 12px;
        border: {hairline};
        min-width: 220px;
        min-height: 220px;
        box-shadow: {drop};
    }}
    .cover-glyph {{
        font-size: 38px;
        font-weight: 700;
        color: {lyric};
    }}

    .corner-tag {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.6em;
        padding: 2px 6px;
        border-radius: 7px;
        border: {hairline};
        margin: 6px;
    }}
    .corner-tag-left {{
        background-color: {root};
        color: {outline};
    }}

    .list-plate {{
        background-color: {dim};
        border-radius: 12px;
        padding: 5px;
        border: {hairline};
        box-shadow: {recess};
    }}
    .list-plate row {{
        background: transparent;
    }}

    .list-header {{
        background-color: {stage};
        color: {score};
        font-family: {mono};
        font-weight: 700;
        border-radius: 7px;
        padding: 5px 8px;
        margin-bottom: 5px;
        border: {hairline};
        box-shadow: {drop};
    }}

    .station-row {{
        padding: 5px 7px;
        border-radius: 7px;
        margin-bottom: 3px;
        background-color: {stage};
        border: {hairline};
        box-shadow: {drop};
    }}
    .station-row:hover {{
        background-color: {wing};
    }}
    .station-row.active {{
        background-color: {seventh};
        color: {hall};
        border-color: {root};
    }}
    .station-row.active label {{
        color: {hall};
    }}
    .station-freq {{
        color: {lyric};
        font-weight: 700;
        font-family: {mono};
    }}
    .station-row.active .station-freq {{
        color: {hall};
    }}
    .station-live {{
        font-size: 0.8em;
        color: {seventh};
    }}
    .station-row.active .station-live {{
        color: {hall};
    }}
    .station-row.active .tag-chip label {{
        color: {lyric};
    }}

    .control-btn {{
        border-radius: 7px;
        min-width: 28px;
        min-height: 28px;
        padding: 0;
        background-color: {wing};
        background-image: none;
        color: {score};
        border: {hairline};
        box-shadow: {drop};
    }}
    .control-btn:hover {{
        background-color: {stage};
    }}
    .control-btn:active {{
        box-shadow: {press};
    }}
    .control-btn.primary {{
        min-width: 36px;
        min-height: 36px;
        border-radius: 9px;
        background-color: {piano};
        background-image: none;
        color: {hall};
    }}
    .control-btn.primary:hover {{
        background-color: {forte};
        color: {hall};
    }}

    .meta-title {{
        font-family: {prop};
        font-size: 1.05em;
        font-weight: 700;
        color: {score};
    }}
    .meta-artist {{
        font-family: {prop};
        font-size: 0.9em;
        color: {forte};
    }}
    .meta-genre {{
        font-family: {mono};
        font-size: 0.85em;
        color: {root};
    }}

    .thread-label {{
        font-family: {mono};
        font-size: 0.75em;
        color: rgba({score_rgb}, 0.28);
    }}
    .thread-label.lit {{
        color: {root};
        font-weight: 700;
    }}

    .tech-badge, .tag-chip {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.72em;
        background-color: {wing};
        background-image: none;
        color: {lyric};
        padding: 2px 7px;
        border-radius: 7px;
        border: {hairline};
    }}
    .tag-chip:hover {{
        background-color: {stage};
        color: {score};
    }}
    .tag-chip.country {{
        color: {sotto};
    }}
    .tech-badge.rec-badge {{
        background-color: {forte};
        color: {hall};
    }}

    .small-badge {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.65em;
        background-color: {dim};
        color: {root};
        padding: 2px 6px;
        border-radius: 6px;
    }}

    .section-rule {{
        border-top: {rule};
        margin: 20px 4px 8px;
        padding: 8px 2px 0;
    }}
    .section-rule label {{
        color: {lyric};
        font-family: {mono};
        font-weight: 700;
        font-size: 10px;
        letter-spacing: 0.14em;
    }}
    .section-rule.gold label {{
        color: {root};
    }}

    .pennant-btn {{
        background: transparent;
        border: none;
        box-shadow: none;
        padding: 0;
    }}
    .pennant-btn:hover {{
        background: transparent;
    }}

    .knob-tag {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.58em;
        color: {rest};
        letter-spacing: 0.05em;
    }}

    .brand-tag {{
        font-family: {mono};
        font-weight: 700;
        font-size: 0.56em;
        letter-spacing: 0.08em;
        color: rgba({score_rgb}, 0.35);
        margin: 6px 8px;
    }}

    popover.context-menu > contents {{
        background-color: {stage};
        background-image: none;
        color: {score};
        border-radius: 12px;
        border: {hairline};
        box-shadow: 0 4px 12px rgba({staff}, {a_drop});
        padding: 10px;
    }}
    popover.context-menu > arrow {{
        background-color: {stage};
        border: {hairline};
    }}
    .context-menu label {{
        color: {score};
        font-family: {mono};
        font-size: 0.85em;
        font-weight: 700;
        margin-top: 4px;
    }}
    .context-menu entry {{
        background-color: {dim};
        color: {score};
        border-radius: 7px;
        padding: 6px;
        border: {hairline};
        box-shadow: {recess};
    }}
    .context-menu entry:focus-within {{
        border: 1px solid {root};
    }}
    .context-menu separator {{
        background-color: rgba({score_rgb}, 0.13);
        min-height: 1px;
        margin: 6px 0;
    }}

    .menu-btn {{
        padding: 6px 8px;
        border-radius: 7px;
        color: {score};
        background-color: {wing};
        background-image: none;
        border: {hairline};
        box-shadow: {drop};
    }}
    .menu-btn:hover {{
        background-color: {stage};
    }}
    .menu-btn:active {{
        box-shadow: {press};
    }}
    .menu-btn.destructive-action {{
        color: {forte};
    }}
    .menu-btn.destructive-action:hover {{
        background-color: {forte};
        color: {hall};
    }}

    .field-entry {{
        background-color: {dim};
        background-image: none;
        color: {score};
        border-radius: 7px;
        padding: 5px 8px;
        border: {hairline};
        box-shadow: {recess};
    }}
    .field-entry:focus-within {{
        border: 1px solid {root};
    }}

    .search-btn {{
        border-radius: 7px;
        padding: 5px 10px;
        border: {hairline};
        box-shadow: {drop};
        background-image: none;
        background-color: {wing};
        color: {score};
        font-family: {mono};
        font-weight: 700;
    }}
    .search-btn:hover {{
        background-color: {stage};
    }}

    .info-panel {{
        background-color: {stage};
        border-radius: 12px;
        border: {hairline};
        box-shadow: {recess};
        padding: 8px;
    }}
    .info-panel.stale, .cover-art.stale {{
        opacity: 0.5;
    }}
    .info-line {{
        font-family: {mono};
        font-size: 0.72em;
        font-weight: 700;
        color: {lyric};
    }}
    """


def load_custom_css():
    global _css_provider
    css = _build_css(palette.load())

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
