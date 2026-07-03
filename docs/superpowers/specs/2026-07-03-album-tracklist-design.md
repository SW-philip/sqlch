# Album Tracklist on Flip-Back Panel — Design

**Date:** 2026-07-03
**Status:** Approved

## Summary

The Now Playing panel's flip-back "ledger" (`sqlch_gui/ui/now_playing.py`,
`_sync_back_plate`) currently just re-shows the single current track's
title/artist — the same info visible on the front of the card. Replace it
with the real album tracklist for the currently playing song, fetched via the
Spotify Web API the app already authenticates against for cover art
(`sqlch/core/spoti.py`). This makes the flip gesture actually reveal new
information, like flipping a record sleeve to read the back cover.

No track-history / recently-played concept is being introduced — that data
doesn't exist anywhere in the app (mpv only exposes the live ICY string) and
isn't the goal here. This is strictly: current track → its album → that
album's tracklist.

## Why piggyback on the existing enrichment pipeline

- `sqlch_gui` already imports `sqlch.core.enrich`/`spoti` in-process (not via
  daemon IPC) and runs `enrich_track()` in a background thread whenever the
  ICY title changes (`metadata.run_enrich`, called from
  `NowPlayingPanel.update`). Results land in the cache the GUI already polls
  (`ENRICHED_JSON`, read via `metadata.get_enriched_meta`).
- `spoti._search_track` already gets back a Spotify `album` object with an
  `id` on every successful match — the tracklist is one more request away
  using data already in hand.
- Reusing this path means no new IPC command, no new polling loop, and the
  same timing behavior cover art already has: the GUI's normal ~1s status
  poll (`update()`) re-renders the back plate if it's open, so the tracklist
  simply appears a few seconds after playback starts, same as cover art does
  today.
- Rejected alternative: fetch on-demand only when the user clicks flip,
  directly from `now_playing.py`. Rejected because it duplicates the
  cache-first logic already in `spoti.py`/`enrich.py` and doesn't benefit
  from the pre-fetch that's already in flight by the time the user flips.
- Rejected alternative: new daemon IPC command to fetch server-side.
  Unnecessary — the GUI process already has direct in-process access to
  `sqlch.core`.

## Components

### 1. `sqlch/core/spoti.py`

- `_search_track` already returns `item['album']['id']` — capture it.
- New function `get_album_tracks(album_id: str, token: str) -> list[dict]`:
  - `GET {base}/albums/{album_id}/tracks?limit=50`, following the `next` link
    in a simple loop for albums over 50 tracks (rare, cheap to handle
    correctly rather than silently truncate).
  - Returns `[{"number": int, "name": str}, ...]`, ordered by track number.
  - Cached by album id in a new `spotify_albums.json` cache file (same
    `cache_dir()` location as the existing track/artist caches). No TTL —
    an album's tracklist doesn't change, matching how artist genres are
    cached today.
- `enrich()` gains two fields on its returned/cached dict: `album_id` and
  `tracklist` (the list above), populated by calling `get_album_tracks` right
  after a confident track match.

### 2. `sqlch/core/enrich.py`

- `enrich_track()`'s Spotify branch copies `album_id` and `tracklist` from
  `spoti.enrich()`'s result into its own `base` result dict, so they ride
  along into `enriched.json` like `album`/`year`/`cover`/`genres` already do.
- No changes to the MusicBrainz fallback branch or `_QUALITY_FIELDS` — a
  missing tracklist just means the GUI falls back to today's view (see
  below), it doesn't affect cache freshness scoring.

### 3. `sqlch_gui/ui/now_playing.py`

- Revert the leftover `self._track_history` line added during an earlier,
  abandoned approach (recently-played ring buffer) — not needed.
- `_sync_back_plate()` becomes a no-arg method (reads `self._cur_artist` /
  `self._cur_title` directly, matching how the rest of the class already
  reads instance state):
  - Look up `meta = metadata.get_enriched_meta(self._cur_artist,
    self._cur_title)`.
  - **If `meta` has a non-empty `tracklist`:** render the album name as a
    header, then one label per track (`"{number}. {name}"`), bolding
    whichever entry's `name` matches `meta["track"]` (the canonical Spotify
    title, not the raw ICY string, which can carry ad-tracking junk or be
    otherwise messy — see `parse_icy`/`_parse_iheart`).
  - **Otherwise** (no enrichment yet, no confident Spotify match ever, or a
    MusicBrainz-only result with no tracklist): fall back to today's
    single-line title/artist view unchanged. This is a deliberate choice —
    the panel should never look broken or show an empty state, and the
    "not enriched yet" and "no match" cases are indistinguishable to the
    user in a way that matters, so they share one fallback rendering.
  - `on_flip_clicked` and the `update()` call site both switch to calling
    `self._sync_back_plate()` with no arguments.

### Explicitly out of scope

- Track durations.
- Auto-scrolling the back-plate `ScrolledWindow` to the current track's
  position on flip.
- Any recently-played / track-history mechanism.

## Error handling

- No Spotify credentials configured (`SPOTIFY_CLIENT_ID`/`SECRET` unset) →
  `spoti._get_token()` already returns `None`, `enrich()` already returns
  `None`, `tracklist` is simply absent → fallback view. No new failure mode.
- Network error fetching album tracks → caught like the rest of `spoti.py`'s
  network calls (existing `requests` exception handling conventions in that
  module); treated as "no tracklist" for that enrichment pass, will retry
  next time the track plays (cache is only written on success).
- Album with >50 tracks → paginated via `next`, see above.

## Testing

No test infrastructure exists in the repo (consistent with the rest of
`sqlch`). Verification is manual, using the working-tree dev launch flow:

1. Play a station airing a well-known, easily Spotify-matched track; flip
   the card within a few seconds (before enrichment lands) → fallback
   title/artist view, no crash, no empty panel.
2. Wait for the ~3s enrichment window, flip again (or leave it flipped) →
   full album tracklist appears, current track bolded.
3. Play an obscure/unmatched track → flip shows the fallback view
   indefinitely, not an empty or broken panel.
4. Change stations while the back is flipped → panel updates to the new
   track's tracklist (or fallback) without needing to flip front/back again.
