# sqlch-gui docked windows (Winamp-style)

## Goal

Replace the slide-out drawer (Library/Discover) with separate windows that
dock magnetically to Now Playing. No width spring, no seam drag, no
crossfade overlap.

## Behavior

- **Three layer-shell surfaces:** Now Playing (`SqlchPopupWindow`, stays
  anchored TOP+RIGHT), Library, Discover. Library/Discover are child
  windows owned by Now Playing and close with it.
- **Toggle:** the NOW / LIBRARY / DISCOVER tabs become independent toggles
  for Library and Discover (both may be open). Opening fades the window in
  (opacity 0→1, ~160 ms); closing fades it fully out, then unmaps. Windows
  never animate size or position on toggle.
- **Default placement:** flush against the left edge of the nearest open
  window to the left (Now Playing → Library → Discover), `DOCK_GAP` px gap,
  top-aligned with Now Playing.
- **Dragging:** each docked window has a drag handle (its header strip).
  A drag updates layer-shell margins live (anchor TOP+LEFT, margins in
  monitor px). Library/Discover only; Now Playing stays put.
- **Magnetic snap:** on release, if an edge is within `SNAP_DIST` (20 px) of
  an edge of Now Playing or another window, snap flush (edge and
  top/bottom alignment independently). Otherwise stay where dropped,
  clamped on-screen.
- **Groups:** a window snapped to Now Playing (directly or via a chain)
  re-docks automatically when Now Playing's size or the monitor changes. A
  free window keeps its absolute position.
- **Persistence:** `{name: {docked: bool, x, y, open: bool}}` in
  `~/.local/state/sqlch-gui/windows.json`. Missing/invalid file → defaults.

## Structure

- `ui/dock.py` (new): pure geometry. `snap(rect, others, dist)`,
  `default_dock(order, rects)`, `clamp(rect, monitor)`. No GTK, unit-tested
  in `tests/`.
- `ui/dock_window.py` (new): `DockedWindow(Gtk.Window)` base: layer-shell
  init, header drag handle, fade show/hide, margin placement via `dock.py`,
  state load/save. `StationListPanel` and `DiscoverPanel` are hosted as its
  child unchanged.
- `ui/window.py`: delete drawer code (`dropdown_stack`, `dropdown_scroll`,
  spring, seam drag, `_compute_drawer_max`). Keep daemon loop, palette
  reload. `on_nav_selected` toggles the docked windows.
- `ui/controls.py` `NavColumn`: independent toggle state per tab instead
  of one-of-three; `set_active` replaced by `set_open(name, bool)`.
- `ui/banner.py` `TornSeparator`: the seam no longer separates panels and
  loses its drag-handle role; keep the widget only if the polish pass finds
  a use for it, else delete.

## Constraints

- Niri doesn't place layer-shell surfaces and Mod+drag doesn't move them,
  hence the in-app drag. Positions are pixel margins relative to the
  monitor under the surface; on monitor/scale change docked windows
  re-dock and free ones clamp.
- Probing in `StationListPanel` must stop while its window is hidden
  (previous behavior: unmapped with the drawer). Hook it to `map`/`unmap`.
- Colors from `palette`, no hardcoded hex (existing CSS loader).

## Testing

- `tests/test_dock.py`: snap within/outside distance, per-axis snap, chain
  default dock order with a closed middle window, clamp.
- `tests/test_dock_state.py`: round-trip, corrupt file → defaults.
- Manual on desktop: toggle each, both at once, drag-snap, free drag,
  restart restores layout, probes stop when hidden.

## Out of scope (next pass)

Visual polish: screenshot every view, list spots that look unfinished
("wireframe") vs finished, rank, fix. Done after the window work lands.
