# sqlch queue: a cross-source playlist with a radio/media mode

## Goal

Give sqlch a queue. Today `next`/`prev` only cycle radio stations, and nothing
reacts when mpv reaches the end of a file, so a finished track or episode just
stops. The queue holds items from any source and radio stations, advances on
its own, and remembers where parked media left off. It lives in the daemon, so
the CLI, MPRIS (media keys, playerctl, waybar) and the GUI all share it.

## Decisions

- **Explicit queue plus context fallback.** Rows get "Add to queue" and "Play
  next". When the queue is empty, advance continues through the list the
  current item was started from (folder, album, podcast feed).
- **Persistent.** `queue.json` in `data_dir()`, daemon-only writer.
- **Stations are queue entries.** A station entry starts the station and flips
  the mode to RADIO. Radio never ends, so the queue waits at that point.
- **RADIO / MEDIA toggle** on the Playlist pane decides what `next`/`prev` walk.
- **Resume by statefile, not by a paused mpv.** Parked media is a saved
  position, restarted on demand.
- Architecture: a daemon module (`sqlch/core/queue.py`). Not a GUI-only queue
  (the CLI, MPRIS and waybar would have none) and not mpv's own playlist
  (it cannot hold Spotify handoff or radio, and pre-resolved URLs and tokens
  expire).

Out of scope: EQ, scrobbling, named saved playlists, shuffle/repeat, gapless.

## 1. Data model and persistence

`sqlch/core/queue.py` owns the state. `queue.json` in `data_dir()`; the daemon
is the only writer, every write replaces the file atomically, the GUI reads it
directly. A corrupt file is quarantined and the queue starts empty, as in
`follows.py`.

```json
{
  "mode": "media",
  "entries": [
    {"uid": "q1", "kind": "item",    "item":    { ...full Item dict... }},
    {"uid": "q2", "kind": "station", "station": {"id": "...", "name": "...", "url": "..."}}
  ],
  "context": {"source": "local", "path": "Albums/Foo", "index": 3},
  "history": [ ...last 20 played entries... ],
  "resume":  {"entry": { ...an item entry... }, "pos": 412.5}
}
```

- `uid` makes reorder and remove unambiguous when the same item is queued twice.
- Item entries carry the whole Item, so display needs no lookup. Station
  entries carry the id plus a name/url snapshot; a station deleted from the
  library still plays from the snapshot.
- `context` is only consulted when `entries` is empty.
- `history` backs `prev` in media mode.
- `resume` is the parked media slot (section 3).

## 2. Advance logic

**End of playback.** The player hooks mpv's `end-file` event with reason `eof`
and calls `queue.advance()`. A manual stop or quit does not advance. Spotify
handoff has no mpv event, so the existing handoff progress poll treats
"position reached duration, or player stopped" as the end.

**`advance()`**, in order:

1. `entries` non-empty: pop the first.
   - **item** entry: play through the normal `play_item` path.
   - **station** entry: start the station and set mode to RADIO. The queue
     waits; the remaining entries are kept.
2. Else, if `context` is set: play the next sibling in that list.
3. Else stop.

**Failures.** An entry that fails to resolve or play shows a toast and is
skipped. After 3 consecutive failures advance stops.

**Mode.** `mode` is `radio` or `media`.

- RADIO: `next`/`prev` cycle stations, as today.
- MEDIA: `next` is `advance()`. `prev` restarts the current item when more
  than 3 s in, otherwise steps back through `history`.
- Playing a station sets RADIO. Playing an item or advancing through the queue
  sets MEDIA.
- A manual toggle sticks until something of the other kind is played.

## 3. Resume

Parked media is a saved position, not a paused mpv: network URLs and tokens
expire, servers drop idle connections, mpv would hold its cache in RAM, and a
Spotify handoff cannot be paused for hours. A saved position survives a
daemon restart too.

- `resume` is written when media stops or is replaced (a station played over
  it, a manual stop), and every ~5 s while media plays so a crash loses at most
  that much. The position comes from the `time-pos` poll already used for
  progress.
- If a track finishes naturally and the queue moves on to a station, `resume`
  becomes the next queued item entry at position 0.
- Resume points reuse `progress.resume_point`: a position within a few seconds
  of the end restarts from the beginning.

**Toggle behavior.**

- RADIO -> MEDIA: play the `resume` entry from its saved position, replacing
  the station. If `resume` is empty, play the head of `entries`; if that is
  empty too, only the mode changes.
- MEDIA -> RADIO: start `library.last_played_station()`, saving `resume` first.
  If there is no last station, only the mode changes.

## 4. Daemon, CLI and MPRIS

New daemon commands:

| Command | Effect |
|---|---|
| `queue_add` | `{entry, at?, play_next?}`. Inserts at the end, at index `at`, or after the current entry for `play_next`. If `entries` is empty and nothing is playing, the entry plays immediately; otherwise it only queues. |
| `queue_remove` | by `uid` |
| `queue_move` | `{uid, to}` |
| `queue_clear` | empties `entries`, keeps `resume` |
| `queue_play` | `{uid}`: jump to an entry, dropping the entries before it |
| `set_mode` | `radio` or `media`, with the toggle behavior above |

`status` gains `mode` and the queue length. `next`/`prev` dispatch on mode.

CLI:

```
sqlch queue                      # list entries and the current mode
sqlch queue add <id|name|url>
sqlch queue clear
sqlch mode [radio|media]         # show or set
```

`sqlch next` and `sqlch prev` already exist and start honoring the mode.

MPRIS `Next`/`Previous` call the same daemon commands, so media keys,
playerctl and waybar follow the mode. `CanGoNext` is true whenever the queue
has entries or a context sibling exists.

## 5. Playlist pane

A new dockable window registered like the source panes, titled PLAYLIST.

- RADIO / MEDIA toggle in the header strip.
- A row per entry, current one marked: art, title, artist, a station icon on
  station entries, a remove button.
- Drag-reorder inside the pane. Library station rows and source rows are drag
  sources; the pane is a drop target that inserts at the drop position. The
  row menu also gets "Add to queue" and "Play next".
- A clear button, and a status line showing the parked item
  ("resume: Foo, 6:52").
- Reads `queue.json` and refreshes when it changes; all writes go through
  daemon commands.

## 6. Errors

- Unresolvable entries are skipped with a toast; 3 in a row stop advancing.
- Corrupt `queue.json` is quarantined; the queue starts empty.
- A command naming an unknown `uid` returns `{ok: false}`.

## 7. Testing

- `queue.py` unit tests: insert and move positions, persistence round-trip,
  corrupt-file quarantine, context fallback, history for `prev`, the resume
  slot including the near-end rule.
- Daemon tests for every command in section 4.
- Advance test with a fake player: a track ends, a station entry starts, mode
  flips to RADIO, later entries are kept; flipping back resumes at the saved
  position; flipping to RADIO saves `resume` first.
- Drop rule: empty queue and idle player plays; otherwise queues.
- GUI tests for the toggle and drop-position math where the existing GUI tests
  make that practical.

## 8. Implementation notes

Where the implementation plan (`docs/superpowers/plans/2026-10-30-sqlch-queue.md`)
refines the sections above:

- **Modules.** State is `sqlch/core/playqueue.py` (not `queue.py`, which would
  shadow the stdlib module for anyone running from `sqlch/core`). Playback
  logic is `sqlch/core/transport.py`.
- **End detection polls, it does not hook `end-file`.** mpv runs with
  `--keep-open=yes`, so it parks at EOF instead of exiting and the daemon has
  only request/response IPC. A 1 s daemon tick reads `eof-reached`
  (`player.playback_ended()`); Spotify handoff counts as ended within 1 s of
  the end. When nothing is left to play, an mpv item is stopped; a handoff item
  is left to the external player's own autoplay.
- **`now`.** `queue.json` also stores `now` (the playing entry). The playing
  entry is popped from `entries` when it starts, so `play_next` inserts at
  index 0 and the pane shows `now` as its first row.
- **`context` carries the sibling items** (`{"items": [...], "index": n}`), sent
  by the pane with `play_item`, instead of a path to re-browse. It works for
  search results and podcast feeds, and advancing needs no network call.
- **`resume` also stores `dur`**, so the near-end rule (within 10 s of the end
  restarts from the top; before 15 s in, also from the top) needs no lookup.
- **Wire format.** `queue_add` takes `{kind, payload, at?, play_next?}`; the
  daemon builds the entry and its `uid`.
- **Default mode is `radio`**, so behavior before first use is unchanged.
- **Playlist rows have no art thumbnails**; they are text rows like the Library
  pane. Thumbnails are a follow-up.
- Stopping (`stop` command) parks the playing item and clears `now`.
