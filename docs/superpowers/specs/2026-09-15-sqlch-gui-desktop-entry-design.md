# sqlch-gui desktop entry — design

**Date:** 2026-09-15
**Status:** Approved (brainstorm)
**Related:** `2026-09-13-sqlch-wing-drawer-design.md` (rewires the eww ledger
chip away from `sqlch-gui-toggle` to a new eww panel, leaving no
existing UI path to launch `sqlch-gui` itself).

## Goal

Give `sqlch-gui` an XDG desktop entry + icon so it's reachable from
walker (niri's app launcher), since the wing-drawer work removes the
only click path that used to open it.

## Icon

`sqlch_gui/assets/sqlch-gui-icon.svg` — vector-traced from
`~/Downloads/sqrrlch_icon.png` (a squirrel + radio-wave mark). Solid
black fill on transparent background, single `<path>`, square-padded
viewBox. No palette/theme binding — this is a static logo mark, same
treatment as any other app's launcher icon (c.f. uniremote's stock
`tv-symbolic`), not a themed CSS surface.

## Wiring (`nix/home.nix`, inside `config = lib.mkIf cfg.enable { ... }`)

- `xdg.dataFile."icons/hicolor/scalable/apps/sqlch-gui.svg".source` →
  the icon above. Lands at `~/.local/share/icons/hicolor/scalable/apps/`,
  the canonical XDG location any icon-theme-aware resolver (including
  walker/elephant) checks by name — no icon-cache regen required, the
  spec allows uncached lookup.
- `xdg.desktopEntries.sqlch-gui`: `Exec = "sqlch-gui-toggle"` (not
  `sqlch-gui` directly) — reuses the existing kill-if-running/spawn
  PID-file toggle, so activating the launcher entry a second time
  closes the popup instead of stacking a duplicate layer-shell surface.
  `Icon = "sqlch-gui"`, `Categories = [ "AudioVideo" "Player" ]`.

## Out of scope

- No change to `sqlch-gui`/`sqlch-gui-toggle` themselves.
- No icon-theme package, no symbolic recoloring — a flat static SVG.
- Downstream: `~/nixos` flake.lock needs `sqlch` input bumped to this
  commit, then `nrs` (left to Phil; not run autonomously on surface).
