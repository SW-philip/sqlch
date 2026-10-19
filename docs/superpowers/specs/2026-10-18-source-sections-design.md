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
- A new upload produces a **toast only**, shown inside the sqlch window (not a
  desktop notification). No badge, no NEW section.
- Channels are added with a **Follow button on every YouTube video row**.

## 1. Section framework

- A source module may define `sections() -> list[{"id": str, "title": str}]`.
  It is optional. A source without it behaves exactly as today.
- `browse("section:<id>")` returns that section's items. `section:favorites` is
  answered by the pane from `follows.list_favorites(source)` and never reaches
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
- Daemon command: `toggle_favorite` (item). The GUI reads favorites directly
  through `sqlch.core.follows` (writes are atomic renames); only the daemon writes.

## 3. YouTube channels

- `youtube_follows.json` in `data_dir()`: list of
  `{channel_id, name, last_video_id, last_checked}`.
- `make_item` takes an optional `channel_id`. A YouTube video row with a
  `channel_id` shows Follow (or Unfollow when already followed).
- Daemon commands: `follow`, `unfollow`. The daemon owns writes to both files;
  the GUI reads them directly.
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
- New video: the watcher queues one notice `"<Channel>: <Title>"` and updates
  `last_video_id`. More than three new videos from one channel in one poll
  queue one summary notice ("<Channel>: N new videos").
- The first poll after following records the current newest video and queues
  nothing.
- Notices are held in memory in the daemon (newest 20 kept). The daemon command
  `drain_notices` returns and clears them. The GUI calls it from its existing
  1 s daemon monitor loop (every 5th pass) and shows each notice as an
  in-window toast. If the GUI is closed, notices wait and show when it opens;
  they are lost if the daemon restarts.

## 4a. In-window toast

- `sqlch_gui/ui/toast.py`: `Toast`, a `Gtk.Label` styled `.toast`, added as an
  overlay on the cover art's `Gtk.Overlay` in `NowPlayingPanel` (bottom,
  full width, hidden by default). The cover stays the main child and the toast
  is the overlay, per the GTK4 overlay z-order convention, so card height never
  changes.
- `Toast.push(text)` sets the text, shows it, and hides it after 6 s. A toast
  arriving while one is showing is queued and shown after it. The GUI shows at
  most one toast per 6 s window, with no cap on queue length beyond the
  daemon's 20.
- `NowPlayingPanel.show_toast(text)` forwards to it, and `SqlchPopupWindow`
  feeds it from the monitor loop.

## 5. Module layout

- `sqlch/core/follows.py` (new): atomic JSON read/write (temp file + rename),
  favorites API (`add`, `remove`, `is_favorite`, `list_favorites`), follow API
  (`follow`, `unfollow`, `list_follows`, `record_seen`).
- `sqlch/core/watcher.py` (new): polling loop and notice queue, with the clock
  and fetcher injectable.
- `sqlch_gui/ui/toast.py` (new): the toast widget.
- `sqlch/sources/youtube.py`: `sections()`, feed fetch and parse,
  channel-id extraction.
- `sqlch/core/daemon.py`: new commands, including `drain_notices`.
- `sqlch_gui/ui/now_playing.py`, `sqlch_gui/ui/window.py`: toast overlay and
  notice drain.
- `sqlch_gui/ui/source_pane.py`: section row, star, Follow/Unfollow.

## 6. Errors

- A feed failure for one channel is logged and skipped, with no notice. After
  ten consecutive failures for a channel, one "can't reach <Channel>" notice is
  queued, then that channel stays quiet until it succeeds again.
- An unavailable source shows its existing setup hint and loads no sections.
- A corrupt JSON file is renamed to `<name>.bad`, logged, and replaced by an
  empty store. It never raises into the daemon.

## 7. Testing

- `follows`: temp `XDG_DATA_HOME`; atomic write, corrupt-file recovery,
  favorites and follows round trips.
- Feed parsing against a saved sample RSS file.
- `watcher`: fake clock and fetcher; no notice on first poll, one notice per
  new video, summary notice above three, failure counter and its single
  notice, `drain_notices` clears the queue and keeps only the newest 20.
- `toast`: shows text, auto-hides, queues a second toast behind the first
  (timer injectable).
- `source_pane` (same pattern as `tests/test_source_pane.py`): section row
  appears only with sections, star toggles, search then clear returns to the
  section, Follow/Unfollow reflects state.
- Source `sections()` and `section:` browse tests for YouTube, Jellyfin,
  Spotify.

## Out of scope

YouTube account sync, YouTube playlists, unseen badges or a NEW section,
Spotify account playlists.
