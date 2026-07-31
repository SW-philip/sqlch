# Live Radio Transport & Info Redesign

**Date:** 2026-07-31
**Status:** Approved

## Summary

Rework the Now Playing card's transport row and info panel so both match
the mental model of live radio rather than a skippable track player, and
tighten the drawer's visual polish. Four areas:

1. Volume becomes a true VU-meter (segmented pills, no draggable dot);
   Stop/Pause/system-Mute collapse into one prominent stop/play toggle,
   plus a record button moves from the album-art corner badge into the
   transport row.
2. The permanent info panel below the album art drops the
   album-tracklist-enrichment view and instead shows Station / Now
   Playing / Previous-tracks context plus stream diagnostic pills
   (Codec/Bitrate/Buffer).
3. The top status readout drops the volume percentage now that volume is
   shown visually.
4. Drawer polish: Discover's search-bar alignment, the results pane
   filling empty space instead of reading as a void, and a brighter
   accent color on station-card subtext.

A one-line pre-existing bug fix (station id/name unwrap) is a
prerequisite for part 2.

## Why

The current transport row has controls that don't apply to a live
stream — a Stop button distinct from Pause, and a system-level Mute
button distinct from both — because on a live stream, "paused",
"muted", and "stopped" are all just silence; there's no position to
resume from. The volume control is a dot dragged over a decorative,
non-interactive `EqStrip`, which reads as a seek scrubber and invites
exactly the wrong expectation (scrubbing/skipping) on something that
can't be scrubbed. Meanwhile the large info panel below the art is
built around album-tracklist enrichment (real for well-tagged tracks),
but for a typical unidentified live stream it just prints "no track
metadata available" — dead space where station identity, current track,
and recent history could live instead.

## 0. Prerequisite bug fix

`now_playing.py:348-350`: `resp["current"]` is actually
`{"type": "station", "item": station}` (see
`sqlch/core/player.py:297`/`sqlch/core/daemon.py:30`), but `update()`
reads `curr.get("id")` / `curr.get("name", ...)` directly on the outer
dict, which never has those keys. `self._cur_station_id` is therefore
always `None` and the station name always falls back to "Unknown
Station" whenever something is actually playing. Fix:
`item = resp["current"].get("item") or {}`, then read `id`/`name`
(and, for part 2, `frequency`/`group`) off `item`. This also means
`StationListPanel.set_active`'s active-row highlight/mini-EQ (keyed off
`get_current_id()`) starts working correctly as a side effect.

## 1. Volume VU Meter & transport actions (`controls.py`, `now_playing.py`)

**New `VolumeMeter(Gtk.DrawingArea)`** replaces `ThreadSlider`:
- 10 fixed segments ("pills"), each filled/unfilled to represent 10% of
  volume. Filled segments are colored on a green→amber→red gradient
  across the row (same palette hex-to-rgb/shade helpers `ThreadSlider`
  already uses: ROOT/SEVENTH toward the low end, FORTE toward the hot
  end) — a real VU-meter look, not an audio-reactive animation.
- Click maps the click x-position to a segment index and sets volume to
  that segment's level (`emit('value-changed', ...)`, same signal
  contract as today).
- Scroll nudges by the existing 5% step (`_on_scroll` logic carries
  over almost unchanged).
- No drag gesture — `GestureDrag`, `_dragging`, `_on_drag_begin/update/
  end`, `_clear_dragging` are all removed. Simpler than `ThreadSlider`.
- Boost carries over: scrolling up while already at 100% engages the
  existing 120% boost (`boost-toggled` signal, `_pre_boost_vol` handling
  in `now_playing.py` unchanged), drawn as one hot-colored overflow pill
  past the 10 regular segments rather than a dot parked in an overflow
  zone.

**`EqStrip` is untouched** as a class — it stays exactly as-is for the
station-row mini "now playing" indicator in `station_list.py`. Only its
use as the volume-slider's decorative backing in `now_playing.py`
(`self.eq_strip`, `vol_overlay`, `set_measure_overlay`) is deleted, since
the new meter draws its own fill and doesn't need a separate animated
layer underneath.

**Transport row**, left to right: `RecordBubble` → prominent
stop/play toggle → separator → speaker icon → `VolumeMeter`.

- `RecordBubble` (already fully built in `controls.py`, currently
  unused) is instantiated in `now_playing.py`'s control row.
  `record-toggled` → `daemon.send({"cmd": "record", "action": "toggle",
  "mode": mode})`. `update_indicators` calls
  `self.rec_bubble.set_state(self._rec_active, mode)` each poll tick,
  per the widget's existing docstring contract.
- The REC corner badge on the album art (`self.rec_tag`) changes from a
  `Gtk.Button` to a plain `Gtk.Label`: drop `on_record_clicked`, the
  right-click `GestureClick`, and `on_rec_mode_cycle` wiring on it. It
  keeps its text/active-state styling (`_update_rec_tag` logic moves to
  set label text/CSS class instead of button label) as a pure status
  indicator — the transport bar now owns the only click/right-click
  record controls.
- `btn_stop`, `btn_mute` (the wpctl system-mute button), and the
  play/pause icon-swap on `btn_toggle` are removed/repurposed into one
  `.control-btn.primary` button: `on_toggle_play` becomes "send `stop`
  when currently playing, `play` (`__last__`) when idle," rather than
  today's `pause`/`play`. Icon swaps between a mute/stop glyph (playing
  state, click silences) and a play triangle (idle state, click
  resumes). `on_toggle_mute` (wpctl mute toggle) is deleted — the single
  button now covers what a separate system mute button would have done,
  since silence-via-stop and silence-via-mute are indistinguishable on a
  live stream.

## 2. Center info box (`now_playing.py`, replacing `track_list_box`)

The album-tracklist-enrichment view (`_sync_tracklist`'s "header
tracklist render" branch, `metadata.get_enriched_meta(...).tracklist`)
is removed entirely, along with the "no track metadata" fallback text —
both replaced by a single always-present three-line block plus a
diagnostics pill row, still inside the existing `.tracklist-panel`-style
container (renamed `.info-panel`):

- **STATION:** `{frequency:.1f} FM · {name}`, reading `frequency`/`name`
  off the now-correctly-unwrapped `current["item"]`. If ICY genre is
  available (`metadata.get_icy_genre()`), append it as a small trailing
  tag.
- **NOW PLAYING:** `Artist — Title`, or `Live Stream` when no ICY
  artist/title is available (today's `_is_live` case, unchanged
  detection logic).
- **PREVIOUS:** up to the last 3 distinct tracks, newest first, tracked
  client-side — `self._history: deque[tuple[str, str]] = deque(maxlen=3)`
  on `NowPlayingPanel`. Pushed in `update()`'s existing "track actually
  changed" branch (`if artist != self._cur_artist or title !=
  self._cur_title:`), pushing the *previous* `(self._cur_artist,
  self._cur_title)` pair before overwriting, skipped when the previous
  pair was empty (nothing to show yet). Cleared whenever
  `self._cur_station_id` changes so history never bleeds across
  stations. Rendered as "Artist — Title" lines, hidden entirely when
  empty (e.g. a station that's never exposed ICY tags this session).
- **Diagnostics pills**, reusing the existing `.tech-badge`/
  `.small-badge` CSS: `Codec: {get_stream_format()}`,
  `Bitrate: {bitrate}k`, `Buffer: {buffer}%`. `Buffer` is a new
  `daemon.get_stream_buffer()` helper, same `_mpv_get_property` pattern
  as `get_stream_bitrate`/`get_stream_channels`, reading mpv's
  `cache-buffering-state` property (0-100 int, already cheap/local — no
  network calls). Each pill is omitted (not blanked) when its value is
  `None`. No Listeners pill — no reliable data source for it exists in
  this codebase (would require per-station Icecast/Shoutcast stats
  scraping, out of scope).

**Album art overlay simplifies**: the title/artist/genre `caption_box`
overlay (currently docked to the art's bottom edge over a scrim) is
removed — that text now lives only in the info box below. The art keeps
its existing corner badges: LIVE (top-left), format (top-right), REC
status label (bottom-right, now passive per part 1).

## 3. Top status header (`_update_readout` in `now_playing.py`)

Drop the `f"{int(self._vol * 100)}%"` segment. Remaining parts unchanged:
bitrate, channel count (Stereo/Mono/NCh), BT, device name — pure
connection/format state, since the VU meter now shows volume visually.

## 4. Drawer polish

- `discover.py`: tighten `search_box`'s margins so the entry+button row
  sits flush with the tag `FlowBox` below it (margin/spacing values
  only — no structural change; the tag grid is already a 4-per-line
  `FlowBox`, which already matches the "compact grid at the top" ask).
- `discover.py` / `common.py`: give `results_box`'s containing
  `Gtk.ScrolledWindow`/`.list-plate` `vexpand` so it visibly fills the
  space below the tag grid, rather than reading as a void before a
  search runs or when results are sparse.
- `common.py`: recolor `.station-live` (the "♫ 90s90s — DIGITAL WEB"
  subtext in library rows) from the muted FIFTH gray to a brighter
  accent (SEVENTH or ROOT, picked live against the fabric background)
  for readability without clashing with the bold title above it.

## Removed

- `ThreadSlider` class (`controls.py`) — replaced by `VolumeMeter`.
- `_sync_tracklist`'s album-tracklist-enrichment branch and its
  `Gtk.ScrolledWindow`/`track_list_box` scaffolding (`now_playing.py`)
  — the tracklist feature from `2026-07-03-album-tracklist-design.md`
  is fully retired per this pass, not kept as a fallback.
  `_TRACKLIST_HEIGHT`, `_fmt_duration` become unused and are deleted.
- `caption_box` (title/artist/genre overlay on the album art).
- `btn_stop`, `btn_mute`, `on_stop`, `on_toggle_mute` (`now_playing.py`).
- `rec_tag`'s click/right-click handlers (`on_record_clicked`,
  `on_rec_mode_cycle`) — badge becomes passive.
- `self.eq_strip`/`vol_overlay` wiring in `now_playing.py` (the
  `EqStrip` *class* itself is kept for `station_list.py`).

## Explicitly out of scope

- `NavColumn`, `TornSeparator`/seam-drag drawer physics, `PennantTag`/
  `RibbonBanner` shapes — untouched.
- Listeners diagnostic — no reliable data source; not implemented.
- Any change to `library.py`'s data model (no favorite/preset flag is
  being added — the brief's "or a Favorite/Preset Save toggle" phrasing
  was an alternative to the record button, and the record button is the
  one being built, per prior confirmation).
- Station-card frequency badge styling in the library rows (`.station-
  freq`) — only the subtext (`.station-live`) color changes.
- Palette/theme source, fonts, fabric/craft-texture SVG filter —
  untouched.

## Testing

No test infrastructure exists in this repo (consistent with prior
specs). Manual verification via the working-tree dev launch flow:

1. Play a station whose stream exposes ICY track tags: confirm STATION/
   NOW PLAYING/PREVIOUS lines populate correctly, PREVIOUS grows up to 3
   entries as tracks change, and clears when switching to a different
   station.
2. Play a station with no ICY tags: confirm NOW PLAYING shows "Live
   Stream", PREVIOUS stays hidden, and no crash/empty-string artifacts
   appear.
3. Confirm Codec/Bitrate/Buffer pills render with real values while
   playing, and are individually omitted (not blank) if a value is
   unavailable.
4. Confirm the VU meter: click at various x-positions sets volume to the
   expected segment, scroll up/down nudges by 5%, scrolling past 100%
   engages the 120% boost with the hot-colored overflow pill, scrolling
   back down disengages it.
5. Confirm the transport row: RecordBubble left-click toggles recording
   (daemon reflects it within a poll tick), right-click cycles FULL/
   TRACK mode; the corner REC badge on the art updates to match but is
   no longer clickable.
6. Confirm the primary toggle button: click while playing stops
   playback (not just pause — verify via `sqlch status`/daemon state
   that mpv actually stops), click while idle resumes the last station.
7. Confirm the top readout no longer shows a volume percentage, and
   still shows bitrate/channels/BT/device name correctly.
8. Confirm active-row highlighting and the mini-EQ indicator in the
   Library drawer now work (regression check for the part-0 bug fix).
9. In the Discover drawer: confirm the search bar sits flush with the
   tag grid, the results pane visibly fills the space below the tags
   (not a void) both empty and populated, and station-card subtext in
   the Library drawer reads clearly in at least two palette themes.
