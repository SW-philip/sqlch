# sqlch-gui movable Now Playing + live magnet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Now Playing be dragged anywhere (docked windows travel with it), and make snapping feel like a magnet: it clicks in live while dragging, holds, then breaks away, with a quick flash.

**Architecture:** Docking already works by moving a card inside a stationary, output-sized transparent layer surface (`dock_window.py`). Extract that mechanism into a reusable `OverlayCard` helper (Fixed + input region + drag on a handle + flash) that both `DockedWindow` and `SqlchPopupWindow` use. Magnet behavior is a pure function in `dock.py`. Now Playing's position is persisted in `dock_state`.

**Tech Stack:** Python 3, GTK4, gtk4-layer-shell, pycairo, `unittest`.

## Global Constraints

- Repo/worktree: `/home/prepko/sqlch-docked`, branch `docked-windows`. Tests: `python -m unittest tests.<module> -v`. 3 errors in `tests/test_header.py::TestPreviousTracksReserveSpace` are pre-existing on main — ignore.
- Do NOT launch the GUI (it opens on the user's live desktop); the controller/user does live checks.
- Colors only via `palette`/`_build_css`; comments only where the WHY is non-obvious.
- Surfaces are output-sized TOP+LEFT+RIGHT+BOTTOM layer-shell overlays with exclusive zone 0, input region limited to the card rect (an unusable rect must set an EMPTY region so the overlay never swallows input).
- Gesture rule: the `Gtk.GestureDrag` is attached to the stationary root, activates only when the press is inside the handle's bounds (excluding buttons), primary button only, claims the sequence.
- Magnet numbers: snap-in distance 24 px, break-away distance 40 px, flash ~180 ms. Gap convention unchanged (`DOCK_GAP = -8`, flush means `a.right = b.x - gap`).
- Drag-handle affordance on all three strips (Now Playing nameplate, Library, Discover): a subtle grip glyph, low contrast at rest, brighter on hover, grab cursor. Not a labeled "drag bar".
- Commits: lowercase one-liner `sqlch-gui: what`, then blank line + `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Reviewer-flagged safety item already fixed (`4ac3a7e`): keep it intact.

---

### Task A: Magnet logic (pure)

**Files:**
- Modify: `sqlch_gui/ui/dock.py`
- Test: `tests/test_dock.py`

**Interfaces:**
- Produces: constants `SNAP_IN = 24`, `BREAK_OUT = 40` (keep `SNAP_DIST = 20` for the existing `snap`, or make `snap` default to `SNAP_IN` and update tests).
- Produces: `class Magnet(NamedTuple): x: int | None; y: int | None` — the held per-axis snapped coordinate (`None` = free on that axis).
- Produces: `magnet(raw: Rect, others: list[Rect], held: Magnet, snap_in: int = SNAP_IN, break_out: int = BREAK_OUT, gap: int = DOCK_GAP) -> tuple[Rect, Magnet, bool]` — returns the rect to display, the new held state, and `clicked` (True only when an axis newly enters a snapped state this call). Per axis: if currently held and `|raw - held| <= break_out`, stay at the held coordinate (no click); otherwise compute the nearest snap candidate within `snap_in` using the same candidate rules as `snap` (side adjacency with `gap`, edge alignment, stacking; y-alignment only counts against side-adjacent neighbors after the x move); a newly found candidate sets held and `clicked=True`; if none, the axis is free (`None`) and follows `raw`.
- Produces: `screen_edge_rects(area_w: int, area_h: int, margin: int = 12) -> list[Rect]` — zero-width/height edge targets so Now Playing can magnet to the usable-area edges with the 12 px default margin. Document the exact representation chosen and test it (e.g. four thin Rects just outside the area so the existing adjacency rules produce `margin` px clearance; or a dedicated edge pass in `magnet`). Pick whichever keeps `magnet` simple; add tests for left/right/top/bottom.

- [ ] **Step 1: Write failing tests** (exact Rect asserts) in `tests/test_dock.py::TestMagnet`: (a) drag toward NP from 30 px away: not snapped (free, `clicked` False); (b) at 20 px: snaps flush (`clicked` True, held set); (c) continuing to drag 30 px further while held: stays flush, `clicked` False; (d) pull past 40 px from the held coordinate: releases and follows raw; (e) re-approach: `clicked` True again; (f) x held and y free independently; (g) screen-edge snap places the card `margin` px from each edge.
- [ ] **Step 2: Run to verify fail** — `python -m unittest tests.test_dock -v` (new tests fail/ImportError).
- [ ] **Step 3: Implement** `Magnet`, `magnet`, `screen_edge_rects` minimally; reuse candidate helpers from `snap` (refactor shared helpers, keep `snap` behavior and tests green).
- [ ] **Step 4: Run to verify pass**, plus the full test_dock module.
- [ ] **Step 5: Commit** `sqlch-gui: live magnet snap with hold and break-away`.

---

### Task B: OverlayCard extraction, live magnet in docked windows, grip affordance, flash

**Files:**
- Create: `sqlch_gui/ui/overlay_card.py`
- Modify: `sqlch_gui/ui/dock_window.py`, `sqlch_gui/ui/dock_manager.py`, `sqlch_gui/ui/common.py` (CSS), `tests/test_gui_style.py`

**Interfaces:**
- Consumes: `dock.magnet`, `dock.Magnet`, `dock.Rect`.
- Produces: `OverlayCard(window: Gtk.Window, card: Gtk.Widget, handle: Gtk.Widget | None, on_drag: Callable[[Rect], Rect | None] | None = None, on_drop: Callable[[Rect], None] | None = None)` owning: the `Gtk.Fixed` (set as the window's child), `place(rect)` (move card, set size request, update input region incl. the empty-region safety rule), `rect`, input region on map, the stationary-root `GestureDrag` described in Global Constraints (calls `on_drag(candidate_rect)` on every update and uses the returned rect if not None, else the candidate; calls `on_drop(final_rect)` on release only if the rect changed from the drag-start rect), and `flash()` (adds CSS class `dock-flash` to the card, removes it after ~180 ms via `GLib.timeout_add`; re-entrant safe).
- Produces: `grip()` helper (in `overlay_card.py` or `common.py`) returning a small `Gtk.Label` with CSS class `dock-grip` showing a subtle grip glyph (e.g. `⋮⋮` or `⠿`).
- `DockedWindow` is rebuilt on `OverlayCard` (no behavior change besides magnet/flash/grip); `on_drag` calls `manager.magnet_for(name, candidate) -> Rect` which uses `dock.magnet(candidate, other_rects, held[name])`, stores the new held state in the manager (reset at drag start and drop), and calls `flash()` when `clicked`. `commit_drag` keeps its current semantics (docked-vs-free classification, state save, relayout) but takes the already-magnet-snapped rect.
- CSS (in `_build_css`, palette tokens only): `.dock-grip` (rest color, ~0.5 opacity; hover on the handle → full `score` color via `.dock-handle:hover .dock-grip`), `.dock-flash` (brief outline/glow on the card using `score`/`root` palette tokens, fast transition). Extend the CSS test to assert `.dock-grip` and `.dock-flash`.

- [ ] **Step 1: Failing CSS test** for `.dock-grip` and `.dock-flash`; run `python -m unittest tests.test_gui_style -v` → FAIL.
- [ ] **Step 2: Add CSS**; test passes.
- [ ] **Step 3: Implement `overlay_card.py`**, move the card/Fixed/input-region/drag/flash logic out of `dock_window.py` into it (do not change observable behavior of fades, state, retry logic, np_rect, pinning).
- [ ] **Step 4: Rebuild `DockedWindow` on it; add the grip to the handle strip (title left, grip centered/right, close button right); wire the live magnet via the manager.** Remove the now-redundant release-time `snap` call in `commit_drag` (the drop rect is already magnet-snapped); keep clamp.
- [ ] **Step 5: Verify** — `python -m unittest tests.test_dock tests.test_dock_state tests.test_nav_column tests.test_gui_style -v`, `python -c "import sqlch_gui.ui.window"`, `nix run nixpkgs#ruff -- check sqlch_gui/ui/dock_window.py sqlch_gui/ui/dock_manager.py sqlch_gui/ui/overlay_card.py sqlch_gui/ui/common.py` (ignore E402), full suite once.
- [ ] **Step 6: Commit** `sqlch-gui: shared overlay card with live magnet and grip hint`.

---

### Task C: Movable Now Playing

**Files:**
- Modify: `sqlch_gui/ui/window.py`, `sqlch_gui/ui/dock_manager.py`, `sqlch_gui/ui/dock_state.py`, `sqlch_gui/ui/header.py` (grip on the nameplate strip), `tests/test_dock_state.py`

**Interfaces:**
- Consumes: `OverlayCard` (Task B), `dock.magnet`, `dock.screen_edge_rects`.
- Produces in `dock_state`: the state dict gains a key `"np"`: `None` (default = top-right: x = area_w − 12 − w, y = 48, computed at runtime) or `{"x": int, "y": int}` (overlay-surface coordinates of the card). `default_state()`, `load()` (sanitize: ints only, else `None`), `save()` handle it; update `tests/test_dock_state.py` (round-trip, corrupt → `None`, non-int → `None`). The `NAMES` tuple stays windows-only.
- `SqlchPopupWindow` becomes an overlay like the docked windows: anchors on all four edges, exclusive zone 0, no margins (replace the current TOP/RIGHT anchors, `set_margin` calls and `set_default_size(290, -1)`), transparent `dock-overlay` class, its existing `main_box` (with `popup-window`) is the card inside an `OverlayCard`; handle = the Header's nameplate strip (add the grip next to the SQLCH nameplate in `header.py`, keep header tests passing). On map it positions itself from `state["np"]` or the top-right default (clamped to the usable area). Dragging it uses `dock.magnet` against the screen-edge rects (and NOT against docked windows), moves the card live, and **moves all open docked windows with it** (call `manager.relayout()` each update — docked windows use NP-relative offsets so they follow; free windows stay), flashes on a click, and on drop saves `state["np"]` (+ relayout/save).
- `DockManager.np_rect()` now returns the NP card's rect from the `OverlayCard` (position + its natural/allocated size) instead of deriving it from layer-shell margins; keep the same return type/semantics (`Rect | None`) and keep the bounded retry logic working (NP changes now arrive via `OverlayCard.place`/size changes and the existing surface-size signals).
- `DockManager.clamp` for NP uses NP's own overlay size once allocated.

- [ ] **Step 1: Failing tests** in `tests/test_dock_state.py` for the `"np"` key; run → FAIL.
- [ ] **Step 2: Implement state changes**; tests pass.
- [ ] **Step 3: Convert `SqlchPopupWindow` to the overlay + `OverlayCard`**, move position logic and persistence, make `np_rect()` read the card rect, and make dragging NP carry the dock group. Read the current `window.py` and `dock_manager.py` fully first; preserve daemon loop, palette reload, `trigger_library_refresh`, close-request/shutdown.
- [ ] **Step 4: Grip on the nameplate** in `header.py`; adjust header tests only if they assert child counts/order, keeping their intent.
- [ ] **Step 5: Verify** — all of: `python -m unittest tests.test_dock tests.test_dock_state tests.test_nav_column tests.test_gui_style tests.test_header -v` (only the 3 known errors), `python -c "import sqlch_gui.ui.window"`, ruff on touched files (ignore E402), full suite once.
- [ ] **Step 6: Commit** `sqlch-gui: draggable now playing that carries its docked windows`.
