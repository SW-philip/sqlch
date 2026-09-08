# Discover search paging

## Goal

Let the sqlch-gui Discover panel page through RadioBrowser results instead of
stopping at the first 25. Both free-text search and genre-tag browse get a
"Load more" button that appends the next page to the list.

Scope: GUI only. The TUI/CLI Discover pane (`sqlch/core/discover.py`,
`sqlch/tui/app.py`) is a separate codepath and is left unchanged.

## Approach

`radiobrowser` becomes a set of pure functions. The module-level result cache
(`_search_cache`, `_cache_results`, `run_search`, `run_search_by_tag`,
`add_from_search`) is removed — `DiscoverPanel` is the only caller and already
tracks view state, so it owns the accumulated result list and calls
`library.add_url()` directly on import.

Paging uses the RadioBrowser `limit` + `offset` query params, which every
station-list endpoint supports.

## `sqlch_gui/radiobrowser.py`

### `_fetch_stations(url, limit, offset=0)`

- New `offset` parameter.
- Appends `limit` and `offset` as query params, choosing `?` or `&` based on
  whether the URL already has a query string (helper, e.g. `_with_params`).
- Client-side `raw[:limit]` truncation stays as a safety net.
- Normalized dict keys unchanged: `name`, `url`, `favicon`, `tags`, `country`,
  `bitrate`. No `index` key any more.

### `search(query, limit=25, offset=0)`

- Adds `offset=0` default; default `limit` becomes 25 (was 20).
- Folds `hidebroken=true` into the `byname` URL (previously only `bytag` had it).

### `search_by_tag(tag, limit=25, offset=0)`

- Adds `offset=0` default; default `limit` becomes 25.
- Keeps existing `order=votes&reverse=true&hidebroken=true`; the new params are
  appended with `&`.

### Removed

- `_search_cache`
- `_cache_results`
- `run_search`
- `run_search_by_tag`
- `add_from_search`

`download_logo` / `_fetch_logo_url` are untouched.

## `sqlch_gui/ui/discover.py` — `DiscoverPanel`

### New state

- `self._results: list[dict]` — every station shown, in order.
- `self._active_term: str` — the current query or tag.
- `self._active_kind: str` — `"name"` or `"tag"`.
- The next offset is always `len(self._results)`; no separate offset field.
- `self._page_size = 25`.
- `self._search_gen: int` — bumped on every new search; captured by workers to
  drop stale responses.
- `self._load_more_btn` — reference to the button row, or `None`.

### New search (text or tag)

`on_search` and `on_tag_clicked` converge on a helper
`_start_search(kind, term)`:

1. Bump `self._search_gen`.
2. Reset `self._results = []`, record `_active_kind` / `_active_term`.
3. Clear `results_box`, hide discovery container, show reset banner, start
   spinner (unchanged behaviour).
4. Dispatch a worker thread that calls `radiobrowser.search(term, offset=0)` or
   `search_by_tag(term, offset=0)`.

### Load more

- The button is the **last row** appended to `results_box` (a flat, full-width
  `Gtk.Button` with css class `load-more-row`), so it scrolls with the list.
- On click: disable it, set label to "Loading…", dispatch a worker with
  `offset = len(self._results)` and the current `_search_gen`.
- The worker calls the same `radiobrowser` function as the active search.

### Applying results

`_apply_page(gen, results, *, append)` runs on the GLib main loop:

- If `gen != self._search_gen`, discard (stale response from a previous query).
- Stop spinner.
- If not `append` and `results` is empty → show the existing
  "No stations matched query parameters." label, return.
- Remove the old load-more row if present.
- Append a row per station (existing row-building code, factored into
  `_build_row(station)`); extend `self._results`.
- Import button callback captures the station dict:
  `lambda b, st=station: self.on_import(st)`.
- If `len(results) == self._page_size`, append a fresh load-more row;
  otherwise leave it off (end of results).

A short page, an empty page, or a network error all look identical through this
API, so all three simply mean "no button" — the user re-runs the search if they
suspect a transient failure. This is called out as an accepted limitation.

### Import

```python
def on_import(self, station: dict):
    err = library.add_url(station["name"], station["url"])
    if not err and self.win:
        self.win.trigger_library_refresh()
```

(`library` imported at module top, matching `radiobrowser`'s former internal
import.)

### `reset_discovery_view`

Also clears `self._results`, `self._active_term`, and the load-more reference.

## Tests — new `tests/test_radiobrowser.py`

Mock `urllib.request.urlopen` with a context-manager fake returning a canned
JSON array.

- `search` builds a URL containing `limit=25` and `offset=0`; a second call with
  `offset=25` carries `offset=25`.
- `search_by_tag` URL contains `order=votes`, `hidebroken=true`, **and**
  `limit` / `offset`.
- Result dicts have exactly the keys `name`, `url`, `favicon`, `tags`,
  `country`, `bitrate`.
- Empty API response → `[]`; a raised exception → `[]`.

No GUI/GTK test — `test_gui_style.py` stays as the only UI test and does not
touch Discover.

## Out of scope

- TUI/CLI paging.
- Infinite scroll / auto-load on scroll-to-bottom (explicit button only).
- Distinguishing end-of-results from network failure.
- Caching pages to disk.
