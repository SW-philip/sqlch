# Source pane sections, favorites, and YouTube channel follows

## Goal

Give each source pane a menu of sections (favorites, channels, playlists, ...)
and let YouTube channels be followed, with a toast when a followed channel
uploads a new video.

## Decisions

- Sections are **source-defined**. Each source declares the sections that make
  sense for it. sqlch adds FAVORITES to every source itself.
- YouTube needs **no account**. Channels are a list sqlch stores. No playlists,
  no cookies, no subscription sync.
- A new upload produces a **toast only** (sent through the existing
  `notify.notify`). No badge, no NEW section.
- Channels are added with a **Follow button on every YouTube video row**.

## 1. Section framework

- A source module may define `sections() -> list[{"id": str, "title": str}]`.
  It is optional. A source without it behaves exactly as today.
- `browse("section:<id>")` returns that section's items. `section:favorites` is
  answered by sqlch core (`follows.list_favorites(source)`) and never reaches
  the source, so no source can omit it.
- `SourcePane` shows a pill row above the list (for example
  `CHANNELS · FAVORITES`) only when the source has sections. Style matches the
  other flat panes. A section with no items keeps its button and shows an
  empty-state line.
- Search results replace the list as they do now. Clearing the search returns
  to the current section. Folder navigation and back work inside a section.
- Default sections:
  - **YouTube:** CHANNELS, FAVORITES.
  - **Jellyfin:** LIBRARIES (today's root listing), PLAYLISTS, FAVORITES.
  - **Spotify:** SHORTCUTS (today's list), FAVORITES. Account playlists need an
    extra scope and are out of scope.
  - **Local, video:** FAVORITES only.

## 2. Favorites

- A star on every item row in every pane toggles favorite.
- `favorites.json` in `data_dir()` stores full item dicts tagged with their
  source, so a favorite plays without browsing back to it.
- Daemon commands: `toggle_favorite` (item) and `list_favorites` (source).

## 3. YouTube channels

- `youtube_follows.json` in `data_dir()`: list of
  `{channel_id, name, last_video_id, last_checked}`.
- `make_item` takes an optional `channel_id`. A YouTube video row with a
  `channel_id` shows Follow (or Unfollow when already followed).
- Daemon commands: `follow`, `unfollow`. The daemon owns both files so the
  GUI and the watcher never write concurrently.
- CHANNELS lists followed channels. Opening one lists its latest videos through
  the existing yt-dlp `browse` path (`LIST_LIMIT`).
- Existing `sources.youtube.shortcuts` config entries still appear in CHANNELS.

## 4. Watcher

- `sqlch/core/watcher.py`: a daemon thread started in `run_daemon` next to the
  mpris thread.
- Every `poll_minutes` (default 30, config `sources.youtube.poll_minutes`) it
  fetches each followed channel's feed,
  `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`, parses it, and
  compares against `last_video_id`.
- New video: one toast `"<Channel>: <Title>"`, then `last_video_id` is updated.
  More than three new videos from one channel in one poll produce one summary
  toast ("<Channel>: N new videos").
- The first poll after following records the current newest video and sends no
  toast.

## 5. Module layout

- `sqlch/core/follows.py` (new): atomic JSON read/write (temp file + rename),
  favorites API (`add`, `remove`, `is_favorite`, `list_favorites`), follow API
  (`follow`, `unfollow`, `list_follows`, `record_seen`).
- `sqlch/core/watcher.py` (new): polling loop and toast logic, with the clock,
  fetcher and notifier injectable.
- `sqlch/sources/youtube.py`: `sections()`, feed fetch and parse,
  channel-id extraction.
- `sqlch/core/daemon.py`: new commands.
- `sqlch_gui/ui/source_pane.py`: section row, star, Follow/Unfollow.

## 6. Errors

- A feed failure for one channel is logged and skipped, with no toast. After
  ten consecutive failures for a channel, one "can't reach <Channel>" toast is
  sent, then that channel stays quiet until it succeeds again.
- An unavailable source shows its existing setup hint and loads no sections.
- A corrupt JSON file is renamed to `<name>.bad`, logged, and replaced by an
  empty store. It never raises into the daemon.

## 7. Testing

- `follows`: temp `XDG_DATA_HOME`; atomic write, corrupt-file recovery,
  favorites and follows round trips.
- Feed parsing against a saved sample RSS file.
- `watcher`: fake clock, fetcher and notifier; no toast on first poll, one
  toast per new video, summary toast above three, failure counter and its
  single toast.
- `source_pane` (same pattern as `tests/test_source_pane.py`): section row
  appears only with sections, star toggles, search then clear returns to the
  section, Follow/Unfollow reflects state.
- Source `sections()` and `section:` browse tests for YouTube, Jellyfin,
  Spotify.

## Out of scope

YouTube account sync, YouTube playlists, unseen badges or a NEW section,
Spotify account playlists.
