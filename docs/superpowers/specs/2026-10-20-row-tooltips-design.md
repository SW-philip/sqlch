# Row tooltips: full title, metadata, description

## Problem

Row titles are ellipsized and nothing shows the full title or more detail on
hover. Source-pane rows (episodes, songs, videos) and library station rows have
no tooltip. Items carry no description, so there is nothing to show beyond
title/artist/album/date/duration.

## Item field

`make_item` gains an optional `description` (str | None, default None), stored
under the `"description"` key. Sources that cannot supply one leave it None.

## Sources

- **podcasts** (`parse_feed`): fill from the item's `<description>` (fallback
  `itunes:summary`). The text is usually HTML: strip tags, unescape entities,
  collapse whitespace.
- **jellyfin** (`_items`): request `Fields=Overview` and map `Overview` to
  `description` in `_to_item`.
- **youtube**: no description. flat-playlist listings return it empty
  (verified on a real channel), and a per-video fetch is too slow for a list.
- **spotify, local, video files**: nothing to supply.

## Tooltip text (pure functions, no GTK)

New module `sqlch_gui/ui/tooltips.py`:

- `item_tooltip(item) -> str | None`: full title; then a line
  `artist · album · date · duration` (omitting empty parts, using the existing
  `format_date` / `format_duration`); then, if a description exists, a blank
  line and the description truncated to 300 characters with an ellipsis.
  Folders (kind `folder`) get title and metadata only. Returns None when there
  is no title.
- `station_tooltip(station, live_text) -> str`: full name; a line
  `group · <freq>` (frequency formatted as the row shows it); and, when
  `live_text` is non-empty, the live `artist - title` line.

## GUI wiring

- `SourcePane._build_row`: `row.set_tooltip_text(item_tooltip(item))`.
- `StationListPanel._build_station_row`: set the tooltip on the row from
  `station_tooltip(s, "")`. Wherever the live label text is updated
  (`set_active`, `_apply_probe` and the entries loop around line 154), also
  refresh the row tooltip with the same live text.

## Live-track scrolling

The station row's live label (`station-live`) currently ellipsizes. When its
text is wider than the available space it scrolls horizontally inside its box
(marquee) instead: a slow ping-pong that pauses at each end. Short text stays
static, and scrolling only runs while the row is mapped (visible). Implemented as a small
reusable widget (`ScrollLabel`) so the source-pane rows can adopt it later; it
is used for the station-row live label only in this change.

## Testing

- Unit tests for `item_tooltip` and `station_tooltip` (missing fields, folders,
  truncation, live text present/absent).
- Podcast parse test: HTML description stripped and stored.
- Jellyfin test: `Overview` mapped to `description`; `Fields=Overview`
  requested.
- `make_item` test: description defaults to None.
- Widget tests run only where `gi` is available (they are skipped otherwise, as
  with the existing GUI tests).

## Out of scope

YouTube descriptions, per-video fetches, scrolling in source-pane rows,
changing what the visible subtitle line shows.
