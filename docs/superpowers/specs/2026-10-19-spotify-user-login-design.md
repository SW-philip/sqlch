# Spotify user login: your playlists and followed artists

## Goal

Let the Spotify pane show the logged-in user's own playlists (created and
followed, including private ones) and followed artists, and make private
playlist contents readable. Today the source only has app-level
(client-credentials) access, so private playlists are invisible and the user's
library cannot be listed.

## Decisions

- Scope: **My playlists** and **Followed artists**. Not Liked Songs, saved
  albums, or anything that writes to the account.
- Login: **`sqlch spotify-login`** (CLI). No login UI in the GUI. Until logged in,
  the new sections show a hint in the pane's status line.
- OAuth authorization-code flow with **PKCE**. No client secret is used for the
  user flow; the existing client ID from `spotify_env` is reused.
- Scopes: `playlist-read-private playlist-read-collaborative user-follow-read`.

## 1. Login module (`sqlch/core/spotify_auth.py`)

- `login(client_id, port, ...)` binds a one-shot HTTP server on
  `127.0.0.1:<port>`, prints and opens the authorize URL, waits up to 180 s for
  `/callback?code=...&state=...`, checks `state`, exchanges the code with the
  PKCE verifier, and saves the tokens. Redirect URI is
  `http://127.0.0.1:<port>/callback`; default port 8888, configurable with
  `sources.spotify.redirect_port`. The user registers that exact URI on their
  Spotify developer app once.
- Tokens are stored in `data_dir()/spotify_user.json`, mode 0600, written
  atomically (`access_token`, `refresh_token`, `expires_at`).
- `access_token(client_id)` returns a valid token, refreshing when it expires in
  under 30 s. A refresh response without a new `refresh_token` keeps the old one.
  If Spotify answers `invalid_grant`, the token file is deleted and `NotLoggedIn`
  ("Spotify login expired: run `sqlch spotify-login`") is raised.
- `logged_in()`, `clear()` (used by `sqlch spotify-logout`).
- Endpoint base honours the existing `SQLCH_SPOTIFY_AUTH_BASE` override so tests
  can use a fake server.

## 2. CLI

- `sqlch spotify-login [--port N]` and `sqlch spotify-logout`, added to the help
  text. Login needs the app credentials; without them it exits 1 with a message
  naming `/run/secrets/spotify_env`.

## 3. Spotify source

- Requests use the user token when logged in, else the app token. Private
  playlist contents therefore load for shortcuts and for the new section.
- `sections()` = SHORTCUTS, PLAYLISTS, ARTISTS (FAVORITES is added by
  `sections_for`).
- `section:playlists`: `/me/playlists`, 50 per page by offset, capped at 200,
  as playlist folder items. `section:artists`: `/me/following?type=artist`,
  50 per page by cursor, capped at 200, as artist folder items (opening one
  lists albums as today).
- When logged out, both sections raise `Not logged in to Spotify: run
  `sqlch spotify-login``, which the pane shows as "Couldn't load: ...".

## 4. Errors

- Network/HTTP failures during login or refresh surface as `AuthError` with
  Spotify's error code. Browse errors surface through the pane's existing
  "Couldn't load" status.
- A callback with `error=access_denied`, a wrong `state`, or no callback within
  180 s fails the login with a clear message and writes nothing.

## 5. Testing

- PKCE challenge against the RFC 7636 test vector; authorize URL contents.
- Token store: 0600 mode, atomic write, round trip, `clear`.
- `access_token`: valid token reused, expired token refreshed (rotated and
  non-rotated refresh token), `invalid_grant` clears and raises, missing file
  raises `NotLoggedIn`.
- `login` end to end against a fake token endpoint with the browser step
  replaced by an HTTP request to the callback; bad state, denied, and timeout.
- CLI commands with `spotify_auth` patched.
- Source: bearer selection, both sections, paging and caps, logged-out error.

## 6. Unverified assumptions (check before relying on them)

Spotify's 2026 developer-mode changes were not fully readable from docs. To
verify live after the first login:

- Spotify accepts the `http://127.0.0.1:8888/callback` redirect with PKCE.
- `/playlists/{id}/tracks` still returns items for a private playlist with a user
  token (the migration may have renamed or restricted it).
- `/me/following?type=artist` and `/me/playlists` return data for the dev-mode app.

Account requirement: development-mode apps need the app owner on Premium and are
limited to a few users; this is a single-user setup.

## Out of scope

Liked Songs, saved albums, in-GUI login, writing to playlists, client-secret
based user flows.
