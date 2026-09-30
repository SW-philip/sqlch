# sqlch-gui header redesign

Date: 2026-09-30. Status: design approved in conversation, pending written-spec review.
Sibling: `~/nixos/docs/superpowers/specs/2026-09-29-uniremote-house-style-design.md`
(the `Header` this is modeled on: `~/nixos/pkgs/uniremote/src/uniremote/header.py`).

## Goal

The top of the sqlch-gui popup matches uniremote's header: a nameplate row, a
live "plate" (LED + big line + small italic line), and folder-style tabs that
join the card. Everything else in sqlch keeps its current look, info and
behavior.

## Non-goals

- Cover art, LIVE tag, controls, volume meter, record bubble, codec/bitrate/
  buffer pills, the drawer, the torn seam, the library/discover panels.
- Any daemon or metadata change. No new polling: the existing status poll in
  `window.py` already runs.
- A shared package between the two repos. `header.py` is a vendored adaptation
  (sqlch stays independent of the nixos repo); the duplication is accepted.

## Design

Popup is a layer-shell surface (top-right, 290px wide), so no window handle and
no close chip. There is nothing to put in a menu, so no menu chip either.

**Nameplate row:** spaced-caps `SQLCH` (left). Replaces the decorative
`brand-tag` overlay in `now_playing.py` (remove the overlay and label).

**Plate:**
- LED: lit = daemon reachable, hollow = daemon unreachable. Driven by whether
  `daemon.send({"cmd": "status"})` returned a response (`None` = unreachable).
  Not driven by the existing "stale" flag (stale means stopped/idle).
- Big line (bold): the track, exactly what `lbl_now_playing` shows today
  (`artist — title`, `Live Stream`, or `Not Playing`).
- Small italic line: the station line, exactly what `_update_station_line`
  produces today (station name and frequency).
- Stopped but connected: LED lit, plate keeps showing last-known values dimmed
  (today's `stale` behavior, applied to the plate instead of the info panel).
- Disconnected: LED hollow, plate dimmed, small line replaced by a snark line
  (chosen once per connected-to-disconnected transition; short list, dry tone).

**Tabs:** the Mini / Library / Discover buttons become folder tabs joined to
the card (active = accent fill, border continues into the card's top edge).
`NavColumn`'s public surface stays: the `nav-selected` signal and
`set_active(name)` (names `mini`, `library`, `discover`), so `window.py`'s drawer
logic (`on_nav_selected`, `nav_column.set_active(...)`) is untouched.

**Card body after the move:**
- `lbl_station` and `lbl_now_playing` leave the info panel (they live in the
  plate now).
- `lbl_previous` (the previous-track line) and the codec/bitrate/buffer pills
  stay in the info panel, where they are.
- The info panel keeps its cover-width pin.

## Width invariant (the main risk)

`now_playing.py` deliberately pins the info panel to the cover art's width so
station/track text can never resize the popup (comment at the `info_panel`
block). The plate must follow the same rule: both labels ellipsize (single
line, no wrap), the header's width request is pinned to the same measured width,
and no label may contribute natural width. Verify by playing a station with a
very long title and confirming the popup width does not change.

## Styling

- Structure and chip vocabulary follow uniremote's header; colors come only from
  sqlch's palette (`palette.py`/`load_custom_css` in `ui/common.py`), no new
  hardcoded hex. sqlch's outer chunky chrome (card border, shadows) is unchanged.
- New CSS classes are added next to the existing ones in `common.py`, using the
  same palette tokens `RibbonBanner`/`tech-badge` already use.
- The active-tab accent fill must contrast with its text in every theme: check
  the drmis-live palettes, not just the default.

## Structure

- `sqlch_gui/ui/header.py` (new): `Header(nav_column_signal_source, ...)`
  widget: nameplate, plate (`set_track(markup)`, `set_station(markup)`,
  `set_connected(bool)`, `set_stale(bool)`), and the tab row (wraps/replaces
  `NavColumn`'s visuals, same signal and `set_active`).
- `ui/now_playing.py`: build the header at the top of the card instead of the
  nav row; route `lbl_station`/`lbl_now_playing` updates to the header; drop
  `lbl_brand`; `_set_stale` also dims the plate.
- `ui/window.py`: pass connection state (`resp is not None`) to
  `now_playing.update(...)` / header from the existing poll (around line 316).
- `ui/common.py`: new CSS classes; `NavColumn` styling retired or reused.

## Testing

- Existing tests keep passing (`pytest` in `~/sqlch`).
- Unit: any pure logic (snark selection on transition, connected/stopped/idle
  state mapping) lives in plain functions with tests; GTK glue is verified by
  running.
- Visual (screenshot + Phil's eyeball): connected+playing, connected+stopped,
  daemon stopped (disconnected), long-title width check, drawer open/close via
  the tabs, a few themes.

## Risks

- Width invariant above.
- `NavColumn` may carry styling the tabs need to reproduce (torn seam
  alignment with the drawer): read its current CSS before replacing.
- "Match uniremote" vs "keep sqlch's aesthetic": header follows uniremote's
  layout/chips but inside sqlch's palette; the exact blend is an eyeball call.
