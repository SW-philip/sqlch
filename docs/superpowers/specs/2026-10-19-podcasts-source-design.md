# Podcasts source

## Goal

A podcast pane that searches several podcast directories at once, plays
episodes through mpv, and keeps a list of shows you follow. It is its own
source, separate from Radio and Spotify.

Later phases, not built here:

1. Resume position for episodes (`progress.py` already does this for video).
2. A toast when a followed show posts an episode (the watcher already does this
   for YouTube channels).
3. Add a show by pasting its URL from any app, site, or Spotify. It becomes
   available only if you are subscribed, otherwise sqlch says you need to
   subscribe.
4. Spotify shows.

## Decisions

- **Directories:** Apple Podcasts search (no key) and Podcast Index (free key
  and secret). Podcast Index is skipped when no key is configured, so Apple
  alone works. Spotify is left out: its API finds shows but cannot stream them.
- **Playback:** the RSS enclosure URL goes to mpv. Episode titles, dates,
  durations, and art come from the feed.
- **Following** is separate from favorites. The star marks a favorite episode;
  Follow saves a show.
- **Grouping** is a generic `SourcePane` feature that a source turns on, the
  same way `HAS_DATES` turns on "Oldest first".
- **Spotify** loses its SHORTCUTS section. The config has no shortcuts, so
  nothing is lost.

## 1. Source module

`sqlch/sources/podcasts.py`, registered in `_MODULES` as `podcasts`.

- `NAME = "podcasts"`, `TITLE = "PODCASTS"`, `LABEL = "Podcasts"`,
  `HAS_DATES = True`, `GROUPINGS = ("source", "genre", "az")`.
- `available()` is always true (Apple needs nothing).
- `sections()` returns FOLLOWING. `sections_for` adds FAVORITES.
- `search(q)` queries both directories in parallel, each with its own timeout,
  and merges results on the normalized feed URL (scheme and `www.` dropped,
  trailing slash dropped, lowercased host). Each result is a show folder:
  `{kind: "folder", path: "feed:<url>", feed_url, genre, providers, art,
  artist: <author>}`. `providers` lists every directory that returned the show,
  in a fixed order (`apple`, `podcastindex`).
- If one directory fails, the other's results come back along with a warning.
  If both fail, `search` raises and the pane shows "Couldn't load: ...".
- `browse("section:following")` returns followed shows from the store, in the
  same folder shape, with no network.
- `browse("feed:<url>")` fetches and parses the RSS feed into episode tracks:
  id = guid (else enclosure URL), title, `date` (pubDate as epoch), duration
  (`itunes:duration` as seconds, `HH:MM:SS`, or `MM:SS`), art (episode
  `itunes:image`, else the channel's). Episodes without an enclosure are
  skipped. Newest first.
- `resolve(item)` returns `Target(enclosure_url, meta={title, artist: show,
  album: show, art})`. The episode item carries the enclosure URL, so resolve
  needs no network.

`sqlch/sources/_podcast_dirs.py` holds the two directory clients, using urllib
only (the GUI environment has no `requests`):

- Apple: `https://itunes.apple.com/search?media=podcast&entity=podcast&term=`.
  Uses `feedUrl`, `collectionName`, `artistName`, `primaryGenreName`,
  `artworkUrl600`. Results without `feedUrl` are dropped.
- Podcast Index: `https://api.podcastindex.org/api/1.0/search/byterm?q=`, with
  the `X-Auth-Key`, `X-Auth-Date`, and `Authorization` (sha1 of
  key + secret + date) headers. Uses `url`, `title`, `author`, the first value
  of `categories`, `artwork`. Credentials come from
  `PODCASTINDEX_API_KEY` / `PODCASTINDEX_API_SECRET` in the environment, else
  from `sources.podcasts.env_file` (default `/run/secrets/podcastindex_env`),
  parsed like Spotify's env file.
- Base URLs can be overridden with `SQLCH_APPLE_PODCASTS_BASE` and
  `SQLCH_PODCASTINDEX_BASE` for tests, like `SQLCH_SPOTIFY_BASE`.

`make_item` gains optional `genre`, `providers`, `feed_url`, and `url` (the
enclosure) fields, defaulting to None.

## 2. Following

- `follows.py` gets a third store, `podcast_follows.json`: a list of
  `{feed_url, title, author, art, genre, providers}`. It has the same rules as
  the other two stores: only the daemon writes, the GUI reads directly, and
  writes replace the file atomically.
- Functions: `list_podcasts()`, `followed_feeds()`, `follow_podcast(row)`,
  `unfollow_podcast(feed_url)`. A duplicate follow does nothing.
- Daemon commands: `podcast_follow` (item) and `podcast_unfollow` (feed_url).
  Both reject anything that is not an http(s) URL.
- `SourcePane` shows the Follow / Unfollow button when an item has
  `channel_id` (YouTube, unchanged) or `feed_url` (podcast).
  `_with_marks` reads followed feeds alongside followed channels. Unfollowing
  in FOLLOWING removes the row, just as unfollowing in CHANNELS does.

## 3. Grouping in SourcePane

- When the source has `GROUPINGS`, the search row gets a sort pill showing the
  current mode (`SOURCE`, `GENRE`, `A–Z`). A click moves to the next mode. The
  mode lasts for the session and starts at SOURCE.
- Grouping applies only to lists of show folders (search results and
  FOLLOWING), not to episode lists or FAVORITES. Inside a show, the existing
  "Oldest first" toggle applies instead.
- **SOURCE:** one header per provider (`APPLE PODCASTS`, `PODCAST INDEX`), then
  a header per genre, then shows A–Z. A show from both directories appears
  under each.
- **GENRE:** one header per genre (A–Z; `Other` last for shows with none),
  then shows A–Z, each tagged with its providers (`apple·pi`).
- **A–Z:** a flat list, each row tagged with its genre.
- Headers are rows styled like the Library's collapsible favorites categories.
  Clicking one hides or shows its rows without reloading. Collapse state
  resets when the list reloads.
- Grouping is done in `_fill()` from the loaded items. Changing modes never
  hits the network.

## 4. Spotify

- `sections()` returns PLAYLISTS and ARTISTS. `browse(None)` returns
  `section:playlists`.
- `_shortcuts()`, `_REF`'s use for shortcuts, and the shortcuts line in `HINT`
  are removed. `_REF` stays if anything else uses it.

## 5. Errors

| Case | Result |
|---|---|
| One directory down or times out | Results from the other, status line "Podcast Index unavailable" (or Apple) |
| Both directories down | "Couldn't load: ..." |
| No Podcast Index key | Apple only, no warning |
| Feed fetch or parse fails | "Couldn't load: ..." inside the show |
| Episode without an enclosure | Skipped |
| Follow or unfollow fails | Existing "Couldn't update follows" status |

The partial-results warning travels with the results. `search` returns a list
whose items are normal, and the module keeps the last warning in
`last_warning()`, which the pane reads after `search` returns, in the same
worker.

## 6. Tests

pytest with fakes and no network, following the existing `test_source_*`
files.

- `test_source_podcasts.py`: Apple and Podcast Index parsing; the Podcast
  Index auth header; merging and deduping on normalized feed URLs; provider
  order; one directory down; both down; no key means Apple only; RSS parsing
  (enclosure, guid fallback, the three duration formats, missing image,
  missing enclosure); `resolve` meta; `section:following` reads the store.
- `test_follows.py`: podcast store round trip, duplicate follow ignored,
  unfollow.
- `test_daemon_follows.py`: `podcast_follow` / `podcast_unfollow`, bad URL
  rejected.
- `test_source_pane.py`: the sort pill exists only with `GROUPINGS`; each mode
  gives the right header and row order; cycling modes reloads nothing; the
  follow button shows for `feed_url`; episode lists are not grouped.
- `test_source_spotify.py`: sections are PLAYLISTS and ARTISTS; shortcut tests
  removed.
- `test_sources.py`: podcasts is registered.
