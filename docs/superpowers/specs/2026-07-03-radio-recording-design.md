# Radio Recording — Design

**Date:** 2026-07-03
**Status:** Approved

## Summary

Add stream recording to sqlch. A recording captures the exact bytes mpv is
playing (via mpv's `stream-record` property — bit-perfect, no re-encode, no
second connection) and is labeled with the metadata sqlch already collects
(ICY artist/title, enrichment album/year/genre, station name). Two modes:

- **full** — one continuous file per press-to-stop session, plus a sidecar
  tracklist of everything that aired.
- **track** — streamripper-style: rotate to a new file on each ICY title
  change, each file tagged as an individual song.

Surfaces: a two-detent record knob in the GUI, and `sqlch record` in the CLI.
Recordings land in `~/Music/radio/<Station>/`.

## Why mpv stream-record (decision record)

- Records exactly what the user hears; ad-insertion servers (iHeart, AIS —
  see comments in `sqlch_gui/icyprobe.py`) front-load fresh connections with
  pre-roll ads, which rules out a parallel ffmpeg capture connection.
- No extra bandwidth, no new long-running process; controlled over the
  existing mpv IPC socket (`set_property stream-record <path>` starts,
  `""` stops).
- Lossless: the raw dump is remuxed with `ffmpeg -c copy`, never re-encoded.
- Rejected alternatives: parallel ffmpeg capture (double bandwidth, pre-roll
  ads, drift from what's heard); PipeWire capture (lossy re-encode of decoded
  PCM, extra dependency).

## Components

### 1. `sqlch/core/recorder.py` (new, runs inside the daemon)

Owns all recording state:

- mode (`full` | `track`), active flag
- current raw dump path, session start time
- station dict (name, id, url)
- tracklist: list of `(elapsed_seconds, artist, title)`

Public API:

- `start(mode, station)` — begin recording; error if mpv isn't playing.
- `stop()` — stop and finalize.
- `on_track_change(artist, title)` — called by the daemon's existing
  `_watch_metadata` thread on each ICY title change. Track mode: rotate
  `stream-record` to a fresh raw file and finalize the previous one in a
  background thread. Full mode: append to the tracklist.
- `status()` — `{active, mode, elapsed, file, station}` for frontends.

Raw dumps stage in `<recordings_dir>/.incoming/` until finalized. Failed
finalizes leave the raw file there and fire a desktop notification
(`notify.notify`).

### 2. Finalize step (per closed raw file)

1. ffprobe detects codec → container: `aac→.m4a`, `mp3→.mp3`, `vorbis→.ogg`,
   `opus→.opus`, else `.mka`.
2. `ffmpeg -c copy` remux into the final path with embedded tags.
3. Filenames are sanitized (no `/`, control chars; collision-suffixed).

**Track mode:** `~/Music/radio/<Station>/<Artist> - <Title>.<ext>` tagged
with artist/title + album/year/genre from the enrichment cache
(`enrich.enrich_track` results, already populated by the daemon's metadata
watcher). First and last files of a session are inherently partial → filename
gets a ` (partial)` suffix.

**Full mode:** `~/Music/radio/<Station>/<Station> - YYYY-MM-DD HHMM.<ext>`
tagged with station (album), date, ICY genre. Sidecar
`<same-basename>.tracklist.txt` with one `[mm:ss] Artist - Title` line per
track that aired.

### 3. Daemon protocol + lifecycle (`sqlch/core/daemon.py`, `player.py`)

- New command: `{"cmd": "record", "action": "start"|"stop"|"toggle",
  "mode": "full"|"track"}` → `{ok, recording}`.
- `status` reply grows a `recording` block: `{active, mode, elapsed, file}`.
- `player.stop()` and `player.play_station()` finalize any active recording
  before tearing down / replacing mpv — station switches never lose a take.
- `record start` while nothing is playing → `{ok: false, error}`.

### 4. CLI (`sqlch/cli/main.py`)

- `sqlch record [--full|--track]` — start (default `--full`). If already
  recording, prints status instead of double-starting.
- `sqlch record stop` — stop and finalize.
- Requires the daemon (recording lives in the daemon's mpv); clear error
  otherwise. Help text updated.

### 5. GUI record knob (`sqlch_gui/ui/knob.py`, `now_playing.py`, `daemon.py`)

- New `RecordKnob(Gtk.DrawingArea)` drawn in the same Cairo style as
  `RotaryKnob`, but a two-detent switch: pointer snaps to FULL or TRACK.
- Right-click (`GestureClick`, button 3) spins the detent; left-click
  (button 1) sends `record toggle` with the selected mode.
- Joins the hub row in `NowPlayingPanel`: record | stop | volume | mute.
- While recording: red lamp/ring on the knob and a `REC 03:12` badge in the
  readout strip. State comes from the `recording` block in the existing
  1-second `_daemon_monitor_loop` status poll — the knob reflects daemon
  truth, so GUI and CLI can't drift.
- Styled per the Paper Mario / LBP system aesthetic (palette.sh conventions).

### 6. Config

- `recordings_dir` key in `~/.config/sqlch/sqlch.json` overrides the default
  `~/Music/radio`.

## Error handling

- Not playing / no mpv socket → start fails with a clear error (CLI message,
  GUI knob stays off on next poll).
- ffmpeg/ffprobe failure or disk full → raw file kept in `.incoming/`,
  desktop notification; recording state cleared.
- Daemon killed mid-recording → raw dump survives in `.incoming/` (no
  auto-recovery in v1; documented behavior).
- ICY track boundaries have a few seconds of slop — inherent to the medium;
  accepted, not fought.

## Testing

No test infrastructure exists in the repo. Verification is manual end-to-end:

1. Record a live station in full mode → file lands in
   `~/Music/radio/<Station>/`, plays, has tags + tracklist sidecar.
2. Record in track mode across ≥2 track changes → per-song tagged files,
   partial suffixes on first/last.
3. Switch stations mid-recording → recording finalizes cleanly first.
4. `sqlch record` CLI: start/stop/status, daemon-not-running error.
5. GUI knob: detent spin on right-click, arm/stop on left-click, REC badge.
