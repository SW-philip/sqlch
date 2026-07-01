# sqlch-gui Visual Refresh — Design Spec

**Date:** 2026-07-01
**Status:** Approved for implementation

---

## Goal

The current sqlch-gui popup (Now Playing / Station List / Discover panels) is too sparse — large dead space below the Now Playing controls, and a completely blank Discover panel before a search. This spec fills that space with content rather than shrinking the window, and tightens the neubrutalist shadow/border weight on inner elements so it reads as bold rather than balloony, while keeping the outer window/sidebar frame chunky.

Out of scope for this pass: audio-reactive visualizer (tabled — see Future Work), favorites/pinning, window resizing.

---

## Visual style: chunky outer, tightened inner

Keep the window footprint at 440x500. The bold, hard-shadow neubrutalist look stays, but only on the outer chrome:

**Keep as-is (outer chrome):**
- `.popup-window` — 3px border, 10px/10px offset shadow
- `.sidebar` — 3px border, 6px/6px offset shadow

**Tighten (inner elements) — from 2-3px border / 3-5px shadow down to:**
- `.card`, `.cover-art`, `.list-header`, `.station-row`, `.station-row.active`, `.control-btn`, `.tech-badge` → 2px border, 4px/4px offset shadow (2px/2px for small elements like tech badges)

**Bump up (sidebar nav buttons — part of outer chrome, currently under-weighted relative to the sidebar frame):**
- `.nav-btn:hover` → shadow increases from 2px/2px to 4px/4px
- `.nav-btn.active` → shadow increases from 3px/3px to 5px/5px

This was validated visually via mockup: side-by-side comparison of border/shadow weights, then a composed full-panel mockup of all three views, both approved by the user.

**Background texture:** `.popup-window` and `.sidebar` switch from a flat background-color fill to a subtle diagonal `linear-gradient(160deg, hi, lo)` using palette pairs that already exist but are unused today: `GRAD_HALL_HI`/`GRAD_HALL_LO` for the main window, `GRAD_STAGE_HI`/`GRAD_STAGE_LO` for the sidebar. No new colors are introduced. `sqlch_gui/palette.py`'s `_DEFAULTS` needs fallback entries added for these four keys (matching the Rosé Pine Moon defaults already there) since they aren't currently in `_DEFAULTS`, only in the active raven theme's `palette.sh`.

---

## Now Playing panel: hero cover art

Replace the small 80px left-aligned thumbnail + right-aligned text layout with a centered hero layout:

- Cover art grows from 80px to ~120px, centered horizontally at the top of the card
- Title and artist labels center-align below the cover art (currently left-aligned next to the thumbnail)
- Genre label, controls row, volume row, and tech badges row are unchanged in function, just re-flowed to follow the centered art vertically
- `NowPlayingPanel.__init__` in `sqlch_gui/ui/now_playing.py` restructures the header `card` from `Gtk.Orientation.HORIZONTAL` to `VERTICAL`, and increases `cover_img.set_pixel_size(80)` → `set_pixel_size(120)`
- `.cover-art` CSS `min-width`/`min-height` in `common.py` update from 80px to 120px to match

**Future work (not this pass):** audio-reactive visualizer was considered but tabled — a real VU meter needs a new mpv audio filter (astats/showvolume) piped and parsed live, which adds a data pipeline and playback-stability risk. A decorative (non-audio-reactive) animated EQ bar was the fallback option discussed if this is revisited later.

---

## Station List panel: tag chip + live track preview

Each row keeps its existing frequency + name, and gains:

1. **Group tag chip** — every row gets a small pill showing the station's existing `group` field (already in the data model, used today only as a section header — e.g. "Unsorted", "Indie"). Rendered right-aligned on the row using the same pill style as the Discover tag chips.
2. **Live track preview** — for the currently-active/playing station's row only, a small italic line appears below the station name showing the current ICY track (artist — title), sourced from the same metadata polling already running in `window.py`'s `_daemon_monitor_loop` / `NowPlayingPanel`. This requires plumbing the current ICY artist/title down to `StationListPanel.set_active()` (currently only receives the active station id) so it can render the line on the matching row.

**Fix-while-touching:** `station_list.py`'s group header label hardcodes `foreground='#6e6a86'` instead of pulling from the palette, which violates the project's "always use palette, never hardcode hex" convention. Since this file is being touched for the tag chip work anyway, fix this to pull from `palette.load()` (e.g. `BAR` or `REST`) the same way `common.py` does.

---

## Discover panel: genre/tag browse grid

Replace the blank empty state (shown before any search) with a grid of clickable genre tag chips: Jazz, News, Rock, Electronic, Classical, Talk, Ambient, Sports, 80s. Clicking a chip runs a tag-based search and populates the results list exactly like a text search does today.

- `sqlch_gui/radiobrowser.py` gains `search_by_tag(tag: str, limit: int = 20)`, hitting RadioBrowser's `/json/stations/bytag/{tag}` endpoint (mirrors the existing `search()` function's structure, sorted by station popularity)
- `DiscoverPanel.__init__` in `sqlch_gui/ui/discover.py` adds the tag grid between the search box and the results scroll area, visible only when `results_box` is empty and no search is in flight; hidden once results are shown or a search is submitted
- Tag chip click reuses the existing `_async_search` / `_apply_results` flow, just sourcing from `search_by_tag()` instead of `search()`

---

## Testing

No existing automated tests cover the GUI layer (GTK4 widget tree). Verification is manual: run `python -m sqlch_gui` (or the packaged `sqlch-gui` binary) and visually confirm each panel against the approved mockups, plus exercise the tag-chip search and the live-track preview against a real playing station.
