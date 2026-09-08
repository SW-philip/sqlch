# Discover Search Paging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the sqlch-gui Discover panel page through RadioBrowser results with a "Load more" button, for both free-text search and genre-tag browse.

**Architecture:** `sqlch_gui/radiobrowser.py` becomes pure functions taking `limit`/`offset` (RadioBrowser query params); its module-level result cache is deleted. `DiscoverPanel` (`sqlch_gui/ui/discover.py`) owns the accumulated result list and appends pages; a flat full-width button as the last list row fetches the next page.

**Tech Stack:** Python 3.11, PyGObject (GTK4), `urllib`, `unittest` (run via `python -m unittest discover -s tests`). No pytest in this environment.

## Global Constraints

- Scope: GUI only. Do **not** touch `sqlch/core/discover.py` or `sqlch/tui/app.py`.
- Page size is 25. A first search still returns 25 results (no behavior change for page 1).
- Tests use `unittest.TestCase`, not pytest. Run the suite with `python -m unittest discover -s tests`.
- Match existing code style in each file (no type-annotation additions beyond what neighbors use, mono/flat CSS vocabulary, existing label strings kept verbatim where noted).
- Commit message trailer for every commit:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01156PacK3qLnyF9Nz6p4HaH
  ```
- Auto-push to `main` after committing is fine (per project convention).

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `sqlch_gui/radiobrowser.py` | Modify: functional `search` / `search_by_tag` with `limit`/`offset`; drop module cache + dead imports | 1 |
| `tests/test_radiobrowser.py` | Create: unit tests for URL building + normalization | 1 |
| `sqlch_gui/ui/discover.py` | Modify: rewire to functional API (Task 1), then add paging state + Load more (Task 2) | 1, 2 |
| `sqlch_gui/ui/common.py` | Modify: add `.load-more-row` CSS rule | 2 |

---

## Task 1: Functional `radiobrowser` API + rewire the panel

**Files:**
- Modify: `sqlch_gui/radiobrowser.py`
- Create: `tests/test_radiobrowser.py`
- Modify: `sqlch_gui/ui/discover.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `radiobrowser.search(query: str, limit: int = 25, offset: int = 0) -> list[dict]`
  - `radiobrowser.search_by_tag(tag: str, limit: int = 25, offset: int = 0) -> list[dict]`
  - Each result dict has exactly keys: `name` (str, stripped), `url` (str), `favicon` (str), `tags` (str), `country` (str), `bitrate` (int | None).
  - `DiscoverPanel` gains `self._results: list[dict]` (all stations currently shown) and `on_import(self, station: dict) -> None`.
  - Removed from `radiobrowser`: `_search_cache`, `_cache_results`, `run_search`, `run_search_by_tag`, `add_from_search`.

---

- [ ] **Step 1: Write the failing test**

Create `tests/test_radiobrowser.py`:

```python
import json
import unittest
from unittest.mock import patch

from sqlch_gui import radiobrowser


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_RAW = [
    {
        "name": "  Jazz FM  ",
        "url_resolved": "http://jazz.example/stream",
        "url": "http://jazz.example/old",
        "favicon": "http://jazz.example/fav.png",
        "tags": "jazz,smooth",
        "countrycode": "GB",
        "bitrate": 128,
    }
]


def _capture(bucket, payload=None):
    body = json.dumps(_RAW if payload is None else payload).encode()

    def _open(req, timeout=0):
        bucket.append(req.full_url)
        return _FakeResp(body)

    return _open


class TestSearchUrlBuilding(unittest.TestCase):
    def test_search_includes_limit_and_offset(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            radiobrowser.search("jazz")
        self.assertIn("byname/jazz", urls[0])
        self.assertIn("limit=25", urls[0])
        self.assertIn("offset=0", urls[0])

    def test_search_offset_advances(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            radiobrowser.search("jazz", offset=25)
        self.assertIn("offset=25", urls[0])

    def test_search_by_tag_keeps_existing_params(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            radiobrowser.search_by_tag("Jazz", offset=50)
        u = urls[0]
        self.assertIn("bytag/jazz", u)
        self.assertIn("order=votes", u)
        self.assertIn("hidebroken=true", u)
        self.assertIn("limit=25", u)
        self.assertIn("offset=50", u)

    def test_blank_query_skips_request(self):
        urls = []
        with patch("urllib.request.urlopen", _capture(urls)):
            self.assertEqual(radiobrowser.search("   "), [])
        self.assertEqual(urls, [])


class TestNormalization(unittest.TestCase):
    def test_result_keys_and_values(self):
        with patch("urllib.request.urlopen", _capture([], payload=_RAW)):
            out = radiobrowser.search("jazz")
        self.assertEqual(len(out), 1)
        self.assertEqual(
            set(out[0]),
            {"name", "url", "favicon", "tags", "country", "bitrate"},
        )
        self.assertEqual(out[0]["name"], "Jazz FM")
        self.assertEqual(out[0]["url"], "http://jazz.example/stream")
        self.assertEqual(out[0]["country"], "GB")
        self.assertEqual(out[0]["bitrate"], 128)

    def test_empty_response_returns_empty(self):
        with patch("urllib.request.urlopen", _capture([], payload=[])):
            self.assertEqual(radiobrowser.search("jazz"), [])

    def test_network_error_returns_empty(self):
        def _boom(req, timeout=0):
            raise OSError("network down")

        with patch("urllib.request.urlopen", _boom):
            self.assertEqual(radiobrowser.search("jazz"), [])
            self.assertEqual(radiobrowser.search_by_tag("jazz"), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_radiobrowser -v`
Expected: FAIL — `test_search_includes_limit_and_offset` fails because the current URL has no `limit=`/`offset=` query params (limit is applied client-side as `raw[:limit]`), and `test_search_offset_advances` fails because `search()` takes no `offset` argument (`TypeError`).

- [ ] **Step 3: Rewrite `radiobrowser.py` fetch + query functions**

In `sqlch_gui/radiobrowser.py`:

Remove the now-unused imports `import re` and `from pathlib import Path` (both are already dead; `LOGOS_DIR` is imported separately from `.`).

Replace `_fetch_stations` and add a helper:

```python
def _with_params(url: str, **params: object) -> str:
    """Append query params to a URL, respecting any it already carries."""
    sep = "&" if "?" in url else "?"
    return url + sep + urllib.parse.urlencode(params)


def _fetch_stations(url: str, limit: int, offset: int = 0) -> list[dict]:
    """Fetch and normalize a RadioBrowser station listing from a query URL."""
    url = _with_params(url, limit=limit, offset=offset)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "sqlch-gui/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    return [
        {
            "name": item.get("name", "Unknown").strip(),
            "url": item.get("url_resolved", item.get("url", "")),
            "favicon": item.get("favicon", ""),
            "tags": item.get("tags", ""),
            "country": item.get("countrycode", ""),
            "bitrate": item.get("bitrate"),
        }
        for item in raw[:limit]
    ]
```

Replace `search` and `search_by_tag`:

```python
def search(query: str, limit: int = 25, offset: int = 0) -> list[dict]:
    """Look a station up by name in the RadioBrowser directory."""
    if not query.strip():
        return []
    url = (
        f"https://{_RB_API}/json/stations/byname/"
        f"{urllib.parse.quote(query)}?hidebroken=true"
    )
    return _fetch_stations(url, limit, offset)


def search_by_tag(tag: str, limit: int = 25, offset: int = 0) -> list[dict]:
    """Look stations up by genre/tag, most-voted first."""
    tag = tag.strip().lower()
    if not tag:
        return []
    # bytag matching is case-sensitive server-side and RadioBrowser tags are
    # normalized lowercase, so lowercasing here is what makes "Rock" match.
    url = (
        f"https://{_RB_API}/json/stations/bytag/{urllib.parse.quote(tag)}"
        "?order=votes&reverse=true&hidebroken=true"
    )
    return _fetch_stations(url, limit, offset)
```

Delete `_search_cache`, `_cache_results`, `run_search`, `run_search_by_tag`, and `add_from_search` entirely (the whole block from `_search_cache: list[dict] = []` near the top and the four functions at the bottom).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_radiobrowser -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Rewire `discover.py` onto the functional API (no paging yet)**

In `sqlch_gui/ui/discover.py`:

Add to the imports near the top (next to `from .. import radiobrowser`):

```python
from .. import library
```

In `DiscoverPanel.__init__`, add after `self.win = parent_window`:

```python
        self._results: list[dict] = []
```

Replace `_async_search` and `_async_search_by_tag` bodies to call the new functions:

```python
    def _async_search_by_tag(self, tag: str):
        results = radiobrowser.search_by_tag(tag)
        GLib.idle_add(self._apply_results, results)
```

```python
    def _async_search(self, query: str):
        results = radiobrowser.search(query)
        GLib.idle_add(self._apply_results, results)
```

In `_apply_results`, add result tracking right after `self.spinner.stop()`:

```python
        self._results = results
```

In `_apply_results`, change the import-button wiring from the index form to the dict form:

```python
            btn_import.connect("clicked", lambda b, st=r: self.on_import(st))
```

Replace `on_import`:

```python
    def on_import(self, station: dict):
        err = library.add_url(station["name"], station["url"])
        if not err and self.win:
            self.win.trigger_library_refresh()
```

- [ ] **Step 6: Verify the panel module still parses and nothing references removed names**

Run:
```bash
python -c "import ast; ast.parse(open('sqlch_gui/ui/discover.py').read()); ast.parse(open('sqlch_gui/radiobrowser.py').read())"
grep -n "run_search\|add_from_search\|_search_cache\|_cache_results\|\bindex\b" sqlch_gui/ui/discover.py sqlch_gui/radiobrowser.py
```
Expected: no output from the `python -c` (parses clean); `grep` finds nothing (exit 1).

- [ ] **Step 7: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS — 56 prior tests + 7 new = 63, `OK`.

- [ ] **Step 8: Commit**

```bash
git add sqlch_gui/radiobrowser.py tests/test_radiobrowser.py sqlch_gui/ui/discover.py
git commit -m "$(cat <<'EOF'
refactor(sqlch-gui): functional radiobrowser search with limit/offset

Drops the module-level result cache; DiscoverPanel now holds the result
list and imports stations directly. No behavior change yet — page size
stays 25.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01156PacK3qLnyF9Nz6p4HaH
EOF
)"
git push
```

---

## Task 2: Paging state + "Load more" button

**Files:**
- Modify: `sqlch_gui/ui/discover.py`
- Modify: `sqlch_gui/ui/common.py` (CSS)

**Interfaces:**
- Consumes from Task 1: `radiobrowser.search(term, offset=…)`, `radiobrowser.search_by_tag(term, offset=…)`, `DiscoverPanel.on_import(station: dict)`, `self._results`.
- Produces: no new public API. Internal: `_start_search(kind, term)`, `_fetch_page(gen, offset)`, `_apply_page(gen, offset, results)`, `_build_row(station)`, `_build_load_more()`, `_on_load_more(button)`.

This task has no automated test (GTK UI, no test harness for it). Verification is: module parses, full unittest suite stays green, and a live dev-instance visual check (per the `sqlch-gui-dev-launch` memory).

---

- [ ] **Step 1: Add paging state fields**

In `DiscoverPanel.__init__`, replace the `self._results: list[dict] = []` line (added in Task 1) with:

```python
        self._results: list[dict] = []
        self._active_term = ""
        self._active_kind = "name"   # "name" | "tag"
        self._page_size = 25
        self._search_gen = 0
        self._load_more_row: Gtk.Widget | None = None
```

- [ ] **Step 2: Add the shared `_start_search` helper**

Add this method to `DiscoverPanel` (place it just above `on_tag_clicked`):

```python
    def _start_search(self, kind: str, term: str):
        self._search_gen += 1
        self._results = []
        self._active_kind = kind
        self._active_term = term
        self._load_more_row = None

        self.discovery_container.set_visible(False)
        label = "Search Query" if kind == "name" else "Active Genre"
        self.lbl_active_filter.set_markup(
            f"{label}: <b>{html.escape(term)}</b>"
        )
        self.reset_banner.set_visible(True)
        self.spinner.start()
        while child := self.results_box.get_first_child():
            self.results_box.remove(child)

        gen = self._search_gen
        threading.Thread(
            target=self._fetch_page, args=(gen, 0), daemon=True
        ).start()
```

Note: the label strings `"Search Query: <b>…</b>"` and `"Active Genre: <b>…</b>"` match the current wording exactly.

- [ ] **Step 3: Reduce `on_search` and `on_tag_clicked` to call the helper**

Replace `on_tag_clicked`:

```python
    def on_tag_clicked(self, tag: str):
        self._start_search("tag", tag)
```

Replace `on_search`:

```python
    def on_search(self, button=None, *args):
        q = self.ent_query.get_text().strip()
        if not q:
            return
        self._start_search("name", q)
```

- [ ] **Step 4: Replace the async workers with `_fetch_page`**

Delete `_async_search` and `_async_search_by_tag`. Add:

```python
    def _fetch_page(self, gen: int, offset: int):
        if self._active_kind == "name":
            results = radiobrowser.search(self._active_term, offset=offset)
        else:
            results = radiobrowser.search_by_tag(
                self._active_term, offset=offset
            )
        GLib.idle_add(self._apply_page, gen, offset, results)
```

- [ ] **Step 5: Extract `_build_row` from `_apply_results`**

Rename `_apply_results` to `_apply_page` and split it. First add `_build_row` (the per-station widget, lifted verbatim from the current loop body):

```python
    def _build_row(self, r: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        row.set_margin_top(3)
        row.set_margin_bottom(3)

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        meta.set_hexpand(True)

        title = Gtk.Label(label=r["name"], xalign=0.0)
        title.set_ellipsize(3)

        sub = Gtk.Label(xalign=0.0)
        sub.add_css_class("meta-genre")
        sub.set_text(r.get("tags", "")[:40])

        meta.append(title)
        meta.append(sub)
        row.append(meta)

        cc = r.get("country", "")
        if cc:
            cc_tag = PennantTag(cc, country=True)
            cc_tag.set_valign(Gtk.Align.CENTER)
            row.append(cc_tag)

        bitrate = r.get("bitrate")
        if bitrate:
            rate_lbl = Gtk.Label(label=f"{bitrate}k")
            rate_lbl.add_css_class("small-badge")
            rate_lbl.set_valign(Gtk.Align.CENTER)
            row.append(rate_lbl)

        btn_import = Gtk.Button(icon_name="bookmark-new-symbolic")
        btn_import.set_tooltip_text("Import into local station library")
        btn_import.connect("clicked", lambda b, st=r: self.on_import(st))
        row.append(btn_import)
        return row
```

- [ ] **Step 6: Write `_apply_page` and the load-more button builders**

Replace what is now the old `_apply_results` body with:

```python
    def _apply_page(
        self, gen: int, offset: int, results: list[dict]
    ) -> bool:
        if gen != self._search_gen:
            return False
        self.spinner.stop()

        if self._load_more_row is not None:
            self.results_box.remove(self._load_more_row)
            self._load_more_row = None

        if offset == 0 and not results:
            lbl = Gtk.Label(label="No stations matched query parameters.")
            lbl.set_margin_top(12)
            self.results_box.append(lbl)
            return False

        for r in results:
            self.results_box.append(self._build_row(r))
        self._results.extend(results)

        if len(results) == self._page_size:
            self._load_more_row = self._build_load_more()
            self.results_box.append(self._load_more_row)
        return False

    def _build_load_more(self) -> Gtk.Button:
        btn = Gtk.Button(label=f"Load {self._page_size} more")
        btn.add_css_class("load-more-row")
        btn.set_hexpand(True)
        btn.connect("clicked", self._on_load_more)
        return btn

    def _on_load_more(self, button: Gtk.Button):
        button.set_sensitive(False)
        button.set_label("Loading…")
        gen = self._search_gen
        threading.Thread(
            target=self._fetch_page,
            args=(gen, len(self._results)),
            daemon=True,
        ).start()
```

- [ ] **Step 7: Update `reset_discovery_view`**

In `reset_discovery_view`, add before `self.discovery_container.set_visible(True)`:

```python
        self._results = []
        self._active_term = ""
        self._load_more_row = None
```

- [ ] **Step 8: Add the `.load-more-row` CSS rule**

In `sqlch_gui/ui/common.py`, add immediately after the `.search-btn:hover { … }` block (ends around line 435):

```python
    .load-more-row {{
        border-radius: 7px;
        padding: 6px 10px;
        margin-top: 4px;
        border: {hairline};
        background-image: none;
        background-color: {wing};
        color: {lyric};
        font-family: {mono};
        font-weight: 700;
        font-size: 0.8em;
    }}
    .load-more-row:hover {{
        background-color: {stage};
        color: {score};
    }}
    .load-more-row:disabled {{
        opacity: 0.55;
    }}
```

(`wing`, `lyric`, `stage`, `score`, `mono`, `hairline` are all already bound as locals in `_build_css`.)

- [ ] **Step 9: Verify parse + no stale references**

Run:
```bash
python -c "import ast; ast.parse(open('sqlch_gui/ui/discover.py').read()); ast.parse(open('sqlch_gui/ui/common.py').read())"
grep -n "_apply_results\|_async_search" sqlch_gui/ui/discover.py
```
Expected: `python -c` silent; `grep` finds nothing (exit 1).

- [ ] **Step 10: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS — 63 tests, `OK`. (`test_gui_style.py` re-parses the built CSS; a syntax slip in the new rule fails there.)

- [ ] **Step 11: Live visual check**

Per the `sqlch-gui-dev-launch` memory: launch the working tree (wrapper env + `LD_PRELOAD` of `libgtk4-layer-shell.so`, `/home/prepko/sqlch` first on `PYTHONPATH`); kill any running instance in a **separate** prior command (`pkill -f "python3 -m sqlch_gui"`). Re-read the wrapper for current nix-store hashes.

Check: search a common term (e.g. "jazz"), confirm 25 rows + a flat "Load 25 more" row at the bottom; click it, confirm the next 25 append and the button returns; repeat until a short page drops the button. Then do the same via a genre pennant. Ask Phil to confirm the look (he screenshots himself if grim is declined). Kill the dev instance by PID afterward.

- [ ] **Step 12: Commit**

```bash
git add sqlch_gui/ui/discover.py sqlch_gui/ui/common.py
git commit -m "$(cat <<'EOF'
feat(sqlch-gui): page through Discover results with a Load more row

Both name and genre-tag searches now fetch 25 at a time; a flat
full-width button as the last list row appends the next page. A
generation token drops stale responses from a superseded query.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01156PacK3qLnyF9Nz6p4HaH
EOF
)"
git push
```

---

## Self-Review

**Spec coverage:**
- `_fetch_stations` offset param + `?`/`&` handling → Task 1 Step 3 (`_with_params`). ✓
- `search`/`search_by_tag` gain `offset=0`, limit 25, byname `hidebroken` → Task 1 Step 3. ✓
- Delete `_search_cache`/`_cache_results`/`run_search`/`run_search_by_tag`/`add_from_search` → Task 1 Step 3. ✓
- Normalized keys unchanged, no `index` → Task 1 Step 3 + test `test_result_keys_and_values`. ✓
- Panel state fields → Task 2 Step 1. ✓
- New search resets state, bumps gen, clears box, fetches offset 0 → Task 2 Step 2 (`_start_search`). ✓
- Load more as last row, flat full-width, `load-more-row` class, disable+"Loading…" → Task 2 Steps 6, 8. ✓
- Button shown only when last fetch == page_size → Task 2 Step 6. ✓
- Stale-response guard via generation token → Task 2 Steps 2, 6. ✓
- `on_import` takes dict → `library.add_url` → Task 1 Step 5. ✓
- `reset_discovery_view` clears results/term/load-more → Task 2 Step 7. ✓
- Tests: URL has limit+offset, offset advances, bytag keeps order params, normalization keys, empty→[], error→[] → Task 1 Step 1. ✓
- No TUI/CLI changes → Global Constraints; no task touches those files. ✓

**Placeholder scan:** No TBD/TODO; every code step has literal code. "Add appropriate error handling" not used — the `_apply_page` end-of-results / error behavior is spelled out. ✓

**Type consistency:** `search(query, limit=25, offset=0)` / `search_by_tag(tag, limit=25, offset=0)` identical in interfaces block, Task 1 Step 3, and tests. `_apply_page(gen, offset, results)` signature matches its `GLib.idle_add` call in `_fetch_page`. `_build_load_more` / `_on_load_more` / `_build_row` names consistent between Steps 5, 6 and the interfaces block. `self._load_more_row` used in Steps 1, 2, 6, 7 with the same name. ✓
