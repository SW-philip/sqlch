# sqlch sources: multi-source panes and a rolling radio buffer

## Goal

Turn sqlch from a radio player into a small modular media front end. Each
media source (local files, Jellyfin, YouTube, internal video, Spotify) gets
its own docked pane in the existing Winamp-style window system. Radio gains
a rolling one-hour seekable buffer. Radio stays the core: the Library and
Discover panes are unchanged.

## Scope and decomposition

This is a series of independent cycles, each with its own plan:

1. **Framework + Local source** (this spec, sections 1-5). Proves the design.
2. **Radio timeshift** (section 6). Touches radio playback only.
3. **Jellyfin**, 4. **YouTube**, 5. **Internal video**, 6. **Spotify**: one
   source module each (section 7 lists per-source notes). Spotify last
   because it has the most unknowns.

Out of scope for this series: a video pane rendered inside the GTK app
(video plays in its own mpv window), overflow handling when many panes are
chained (the existing clamp keeps free windows on-screen), cross-source
queues/playlists.

## 1. Source modules

New package `sqlch/sources/`. A source is a module exposing:

- `NAME: str` (registry key, also the dock window name), `TITLE: str`
  (strip title, uppercase), `LABEL: str` (menu label).
- `available() -> bool`: false when config/credentials are missing; the pane
  then shows a one-line setup hint instead of an empty list.
- `search(query: str) -> list[Item]`
- `browse(path: str | None) -> list[Item]`: `None` is the root; folder items
  carry the `path` to pass back.
- `resolve(item: Item) -> Target`: what to play.

`Item` (dict, JSON-safe): `source`, `id`, `title`, `artist`, `album`, `art`
(URL or path or `None`), `duration` (seconds or `None`), `kind` (`track`,
`video`, `folder`), `path` (folders only).

`Target`: `url` (or file path), `video: bool`, `meta` (title, artist, album,
art for Now Playing), and optional `start` (seconds).

`sqlch/sources/__init__.py` holds the registry: `REGISTRY: dict[str, module]`
built from an explicit list of imports (no filesystem scanning), so a missing
optional dependency in one source cannot break the others. Source network
calls run off the GTK main thread and return via `GLib.idle_add`, as
`discover.py` already does.

## 2. Generic pane

`sqlch_gui/ui/source_pane.py`: `SourcePane(Gtk.Box)` takes a source module and
renders: search entry, breadcrumb with back button while browsing, and a
scrolled list of rows (art thumbnail, title, artist/album line, duration).
Click plays; folder rows browse. It uses the same CSS classes and row styling
as `StationListPanel` so the panes look like siblings. Probing/background
work stops on `unmap`, as for the existing panes.

## 3. Window system and navigation

- `dock_state.NAMES` becomes `("library", "discover", *source names)` built
  from the registry. `load()` already ignores unknown names and defaults
  missing ones to closed, so adding a source never needs a migration.
- `DockManager` builds one `DockedWindow` per name; titles come from the
  registry. Library/Discover keep their panels; source panes are
  `SourcePane` instances created lazily on first open (so unused sources cost
  nothing and an unconfigured source cannot slow startup).
- **Nav:** the tab row is 290 px wide and cannot hold seven tabs. LIBRARY and
  DISCOVER stay as tabs. A third tab, SOURCES, opens a popover listing every
  registered source as a toggle row (open dot, label, unavailable ones dimmed
  with their setup hint). Toggling calls the same `DockManager.toggle(name)`.
  `NavColumn.set_open` keeps working for the two tabs; the popover reads
  `DockManager.is_open`.

## 4. Playback

- New daemon command `{"cmd": "play_item", "source": s, "id": i}`. The
  daemon looks the item up (the pane sends the full `item` too, so no
  server-side lookup is needed for search results), calls `resolve`, then
  `player` spawns mpv via a new `play_target(target)` that reuses
  `_spawn_mpv(url, video=...)`. `_current` becomes
  `{"type": "item", "item": item}`.
- `status` / `now_playing_info()` return the item and a `position` /
  `duration` pair for non-live items. mpv properties `time-pos` and
  `duration` are read over the existing IPC socket.
- **Now Playing** shows a source badge, title/artist/art from `meta`, and a
  progress bar with seek when `duration` is known. Radio items keep today's
  live display (the live-radio-transport design deliberately has no scrubber
  for live streams; section 6 revisits that).
- **Video:** `_spawn_mpv` gets `--force-window=yes` and
  `--wayland-app-id=sqlch-video` for `video=True`. A niri window rule in the
  nixos repo (`home/niri/config.kdl.nix`) matches that app-id and applies the
  palette border, rounded corners, shadow, and floating default. Colors come
  from `palette.nix`, no literals.
- Audio-only items keep `--no-video`.

## 5. Config and secrets

`sqlch/core/config.py` gains a `[sources.<name>]` table per source (server
URL, library root, username). Tokens and passwords are read from files named
in config (paths under `/run/secrets`, provisioned by sops-nix in the nixos
repo), never stored in the sqlch repo or its config file. `available()`
returns false and the pane shows the hint when any required value is missing.

## 6. Radio timeshift (separate cycle)

- Radio streams spawn mpv with `--cache=yes --cache-secs=3600
  --demuxer-max-bytes=<N> --demuxer-max-back-bytes=<N>`, sized from the
  stream bitrate so one hour fits (about 60-150 MB at 128-320 kbps, RAM by
  default; `--cache-on-disk` as an opt-in config flag).
- mpv's `time-pos` and `demuxer-cache-time` give the playhead and the live
  edge. Now Playing shows an hour-wide bar with a "behind live" offset, a
  back-15s/forward-15s pair, and a LIVE button that seeks to the edge. The
  bar only appears once there is buffered audio to move into, and is styled
  as a timeline, not the old scrubber-dot the live-radio design removed.
- **ICY titles are tied to the live edge, not the buffered audio.** The
  daemon logs `(wall_time, artist, title)` on every metadata change; the
  displayed title for a playhead position is the last log entry at or before
  `live_wall_time - behind_live`. Previous-tracks, cover enrichment, and
  recording follow the displayed (time-shifted) title, not the live one.
- Pause no longer means silence-and-lose-place: pausing holds the playhead
  and the buffer keeps filling; resuming continues from the same point
  (still within the hour window).
- Station change flushes the buffer. The window never exceeds one hour; the
  oldest audio is dropped as new audio arrives.

## 7. Per-source notes

- **Local:** root from config (`library_root`), `browse` walks directories,
  `search` walks the tree (capped at 200 hits) and matches every query word
  against the relative path. Artist/album/title come from the
  `Artist/Album/NN - Title.ext` path layout; tag reading is deferred so the GUI
  needs no new dependency. Art from `cover.*`. `available()` = root exists.
- **Jellyfin:** REST with API token; `browse` = libraries/albums, `search` =
  `/Items?searchTerm`, `resolve` = direct stream URL with the token.
  Music is audio; movies/shows are `kind=video`.
- **YouTube:** `yt-dlp` for search and format selection (`resolve` returns
  the best matching stream URL, `video=True` for video, audio-only
  otherwise). No account needed for public content.
- **Internal video:** same shape as Local with `kind=video`; may merge into
  Local if the folder layout makes a separate pane pointless.
- **Spotify:** existing `sqlch/core/spoti.py` only enriches metadata. Playback
  needs Premium and librespot or Connect control; `resolve` returns a Target
  with a `handoff` instead of a URL. Designed in its own cycle.

## Testing

- `tests/test_sources.py`: registry builds with a source's import failing,
  `Item`/`Target` validation, Local `browse`/`search` against a temp tree.
- `tests/test_source_pane.py`: row building and folder navigation with a
  fake source (no network).
- `tests/test_dock_state.py`: new names default closed; unknown names ignored.
- Daemon: `play_item` dispatch with a fake source and a stubbed
  `_spawn_mpv`.
- Manual: toggle each pane, dock chains of 3+, video border via the niri
  rule, seek bar on a local file.
