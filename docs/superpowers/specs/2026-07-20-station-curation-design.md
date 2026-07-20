# Station Curation ("algo-killer" presets) — Design

**Date:** 2026-07-20
**Status:** Approved

## Summary

sqlch curates *stations*, not tracks. Where a streaming algorithm optimizes
next-song-similarity against your play history (and converges you toward a
center you already occupy), this feature trusts a station's editorial hand
and evaluates the station as a whole — then gets out of the way.

New stations you add go through an **admission filter** (cheap static
checks) and then a bounded **probation** period where the daemon passively
samples what the station actually plays. At the end of probation, a station
either graduates into your curated **presets** list or quietly stays
uncurated — never deleted, never shamed, still playable by hand.

Scope: this evaluates *new discoveries* as you add them, not a retroactive
re-rank of your existing library. Multi-user/aggregation ideas (favorites,
plays, and engagement pooled across listeners) were raised during design but
are explicitly out of scope — this spec produces per-station metrics shaped
so a future aggregation layer could consume them, but doesn't build one.

## Why station-level, not track-level (decision record)

Track-level recommendation optimizes similarity to what you already like,
which is exactly the mechanism that produces filter-bubble narrowing.
Station-level curation moves the decision up one layer, to where a human
(the station's programmer/DJ) already made the track-level choices. The
metric only has to answer "is this station worth trusting," not "is this
song worth playing" — so a trusted station can play something you'd never
have picked yourself, which is the point.

## Data model

**New module:** `sqlch/core/curation.py` — owns the SQLite database, the
admission filter, the probation poller, and the gate/score evaluation.
Runs inside the daemon so CLI/TUI/GUI all read the same state.

**`sqlch/core/icyprobe.py`** (moved from `sqlch_gui/icyprobe.py`) —
`fetch_stream_title(url)` unchanged, just relocated so the daemon can own
polling independent of whether the GUI is running. `sqlch_gui/icyprobe.py`
becomes a re-export for `station_list.py`'s existing call site.

**Database:** `data_dir() / curation.db` (SQLite, stdlib `sqlite3`, no new
dependency — chosen over the plain-JSON pattern used elsewhere in sqlch
because this data is time-series and benefits from querying, and the
intent is to scale past what a flat file handles comfortably).

Curation state is a separate table keyed by `station_id`, not merged into
`library.json` — the station library stays exactly as it is today.

```sql
-- Your personal listening corpus. Written continuously by the daemon's
-- existing _watch_metadata loop whenever any station is actually playing.
-- This is what candidate tracks are compared against for discovery yield.
CREATE TABLE heard_tracks (
    station_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    first_heard_at INTEGER NOT NULL
);

-- Raw polled observations for stations currently on probation. One row
-- per detected track change; consecutive identical titles collapse into
-- a single row (a poll that sees the same title as last time is not a
-- new play).
CREATE TABLE candidate_probes (
    station_id TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    observed_at INTEGER NOT NULL
);

-- One row per station that has ever entered the curation pipeline.
CREATE TABLE stations_curation (
    station_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,  -- 'candidate' | 'preset' | 'rejected'
    probation_started_at INTEGER NOT NULL,
    probation_ends_at INTEGER NOT NULL,
    score REAL,
    gate_passed INTEGER  -- 0/1, NULL until first evaluation
);
```

Stations added before this feature existed have no `stations_curation` row
and are treated as already-curated — no retroactive probation, consistent
with the new-discoveries-only scope.

## Pipeline

### 1. Admission filter (instant, at `sqlch add` / promoting a search result)

Before a station enters probation at all:

- Bitrate ≥ floor (default 96kbps, configurable)
- Has at least one tag
- Responds to `fetch_stream_title` during admission and has a sane
  RadioBrowser click-count (filters dead/broken entries — not a popularity
  gate, just a liveness check)

Fail → station isn't added. Pass → inserted into `library.json` as usual,
plus a `stations_curation` row: `status='candidate'`,
`probation_started_at=now`, `probation_ends_at=now+14d`.

*(14 days, the bitrate floor, and every threshold below are provisional
defaults — expected to need tuning once there's real data to look at, not
load-bearing design decisions.)*

### 2. Probation

Daemon poller wakes every ~3 minutes, probes every station with
`status='candidate'` via `fetch_stream_title`, writes to `candidate_probes`
on title change. Runs independent of whether that station is actively
playing — this is what decouples the metric from your own listening
patterns (a station backgrounded all week during a busy work stretch
doesn't get an unfair volume advantage; it's sampled on a fixed schedule
regardless of what you're doing).

### 3. Evaluation (once probation ends, or daily lazy check)

**Gate — drift consistency.** Bucket `candidate_probes` by day; compute
artist/tag turnover between consecutive buckets; check whether that
turnover pattern itself repeats across the window rather than being
uniformly random. A station shuffling from an unbounded pool looks flat;
a station with a real format or a DJ shows a repeating rhythm — that
rhythm, not sameness, is the signal. Unique-artist ratio over the window is
a cheap pre-check inside this gate (rules out a 40-song loop before
bothering with the drift correlation).

**Score — discovery yield** (only computed for stations that pass the
gate): % of `candidate_probes` tracks whose `(artist, title)` do not
appear in `heard_tracks`. Higher means more crossover from what you
already know.

### 4. Outcome

- Gate fail → `status='rejected'`. Stays in your library, just not
  surfaced as a preset — still playable by hand.
- Gate pass + score clears threshold → `status='preset'`.
- Gate pass + score below threshold → stays `candidate` for one more
  probation cycle before a final call (avoids killing a good station on a
  slow two weeks).

## Surfaces

- **CLI:** `sqlch add <url>` runs the admission filter automatically;
  reports "added, on probation until <date>" instead of just "added." New
  `sqlch presets` command lists `status='preset'` stations — separate from
  `sqlch list`, which still shows everything. `sqlch info <id>` gains a
  curation block (status, score, days left) when applicable.
- **TUI:** station list gets a small status indicator next to probationary
  stations. No new screen for v1.
- **GUI:** `now_playing.py`'s tracklist-flip interaction logs an explicit
  engagement event as an optional weighting input — not a dependency; the
  gate/score pipeline produces valid presets from polling data alone, so
  CLI/TUI-only usage isn't disadvantaged. `station_list.py` gets the same
  status indicator as TUI. A dedicated curation review panel (browse
  scores, manually override candidate/preset) is reasonable for v2, not
  required to ship the core loop.

## Error handling

- `fetch_stream_title` already returns `None` on any failure (timeout,
  dead stream, malformed ICY); the poller just skips that cycle. A station
  unreachable for its whole probation window naturally fails the gate (no
  diversity, no drift) rather than needing a separate "unreachable" path.
- Probation state lives in SQLite, not in-memory — a daemon restart
  mid-probation resumes polling on the next tick, nothing to recover.
- `curation.db` created lazily on first use, same pattern as
  `library.json`'s `_atomic_write`-on-missing.

## Testing

- Unit tests for the admission filter thresholds, the dedup-on-title-change
  logic, and the gate/score math against synthetic `candidate_probes`
  fixtures (a scripted "random shuffle" station vs. a scripted "repeating
  format" station) — this is the least-obvious code and the most worth
  testing directly.
- Poller scheduling and DB writes get a daemon-level integration test,
  following the pattern `tests/test_recorder.py` already uses for the
  other daemon-owned background job.
- No automated coverage for the actual threshold values (14-day probation,
  96kbps floor, etc.) — those are tuned by living with the feature, not by
  test assertion.

## Open questions / future work

- Exact gate/score thresholds will need tuning against real listening data.
- A curation review panel (GUI) for manual override is deferred to v2.
- The multi-user aggregation idea (pooling favorites/plays/engagement
  across listeners into shared station trust) is explicitly deferred —
  this spec's per-station metrics are structured so they *could* feed that
  later, but no networking/sharing is built here.
