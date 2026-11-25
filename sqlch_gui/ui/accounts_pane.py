"""Accounts pane: sign in to every service that needs it, with each field
explained. Keys are checked against the service before they are saved."""

import json
import os
from urllib.request import urlopen

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from sqlch.core import accounts, spotify_auth
from sqlch.sources import _podcast_dirs, jellyfin, source_config, spotify

from .source_pane import _thread_run

SERVICES = (
    {"id": "spotify", "title": "SPOTIFY APP",
     "help": "Lets sqlch search Spotify. Make a free app on the developer page, add "
             "{redirect} as a Redirect URI, then copy its two keys here. "
             "Changing them signs you out below.",
     "link": ("Developer page", "https://developer.spotify.com/dashboard"),
     "fields": (("client_id", "Client ID", False), ("client_secret", "Client secret", True))},
    {"id": "jellyfin", "title": "JELLYFIN",
     "help": "Plays from your own media server. The key is under Dashboard, API Keys, "
             "on the server. Anyone holding it can control the server, so keep it private.",
     "link": None,
     "fields": (("server", "Address, https://…", False), ("token", "API key", True))},
    {"id": "podcastindex", "title": "PODCAST INDEX",
     "help": "Optional. Adds a second directory to podcast search; Apple Podcasts "
             "works without it. The keys are free and arrive by email.",
     "link": ("Get keys", "https://api.podcastindex.org"),
     "fields": (("key", "API key", False), ("secret", "API secret", True))},
)


def in_use(service: str) -> str:
    """Where the working keys come from: app, system or none."""
    if accounts.get(service):
        return "app"
    if service == "podcastindex":
        cfg = source_config("podcasts")
        found = _podcast_dirs.pi_credentials(cfg.get("env_file") if isinstance(cfg, dict) else None)
    else:
        found = {"spotify": spotify, "jellyfin": jellyfin}[service].available()
    return "system" if found else "none"


STATUS = {"app": "Set up here", "system": "Set up by this computer's configuration",
          "none": "Not set up"}


def player_status() -> str:
    """go-librespot pairing: 204 from /auth/code means nothing is waiting."""
    base = (os.environ.get("SQLCH_LIBRESPOT_URL") or "http://localhost:3678").rstrip("/")
    try:
        with urlopen(f"{base}/auth/code", timeout=2) as r:
            raw = r.read() if r.status == 200 else b""
    except OSError:
        return "The player isn't running"
    if not raw:
        return "Paired"
    try:
        data = json.loads(raw)
    except ValueError:
        data = raw.decode(errors="replace").strip()
    if isinstance(data, dict):
        data = data.get("code") or data.get("user_code") or ""
    return f"Enter code {data} on the pairing page" if data else "Waiting to be paired"


def open_uri(uri: str) -> None:
    # sqlch-gui's launcher pins its own libraries; a browser must not inherit them
    ctx = Gio.AppLaunchContext()
    for var in ("LD_PRELOAD", "LD_LIBRARY_PATH", "GI_TYPELIB_PATH", "PYTHONPATH"):
        ctx.unsetenv(var)
    Gio.AppInfo.launch_default_for_uri(uri, ctx)


def _label(text: str, css: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0, wrap=True)
    lbl.set_natural_wrap_mode(Gtk.NaturalWrapMode.WORD)
    lbl.set_max_width_chars(1)
    lbl.set_hexpand(True)
    lbl.add_css_class(css)
    return lbl


def _button(text: str, clicked) -> Gtk.Button:
    btn = Gtk.Button(label=text)
    btn.add_css_class("row-btn")
    btn.connect("clicked", lambda _b: clicked())
    return btn


class AccountsPane(Gtk.Box):
    def __init__(self, on_changed=lambda: None, run_async=_thread_run, opener=open_uri):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("start", "end", "top", "bottom"):
            getattr(self, f"set_margin_{side}")(8)
        self._changed = on_changed
        self._run = run_async
        self._open = opener
        self.status: dict[str, Gtk.Label] = {}
        self.entries: dict[str, dict[str, Gtk.Editable]] = {}
        self.forget: dict[str, Gtk.Button] = {}
        self.append(_label("Keys you enter here stay on this computer, in a file only "
                           "your user can read, and are kept after a restart.", "acct-help"))
        for svc in SERVICES:
            self.append(self._service(svc))
            if svc["id"] == "spotify":
                self.append(self._spotify_login())
                self.append(self._spotify_player())
        self.refresh()

    # --- building ---

    def _section(self, sid: str, title: str, help: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.append(_label(title, "dock-title"))
        box.append(_label(help, "acct-help"))
        self.status[sid] = _label("", "meta-genre")
        box.append(self.status[sid])
        return box

    def _buttons(self, box: Gtk.Box, *buttons) -> None:
        row = Gtk.Box(spacing=6)
        for b in buttons:
            row.append(b)
        box.append(row)

    def _service(self, svc: dict) -> Gtk.Box:
        sid = svc["id"]
        redirect = spotify_auth.redirect_uri(spotify.redirect_port())
        box = self._section(sid, svc["title"], svc["help"].replace("{redirect}", redirect))
        self.entries[sid] = {}
        for name, hint, secret in svc["fields"]:
            e = Gtk.PasswordEntry(show_peek_icon=True) if secret else Gtk.Entry()
            e.set_property("placeholder-text", hint)
            e.add_css_class("field-entry")
            box.append(e)
            self.entries[sid][name] = e
        self.forget[sid] = _button("Forget", lambda: self.forget_keys(sid))
        self.forget[sid].set_tooltip_text(
            "Deletes the keys entered here and goes back to this computer's configuration")
        self._buttons(box, _button("Check and save", lambda: self.save(sid)), self.forget[sid])
        if svc["link"]:
            text, uri = svc["link"]
            self._buttons(box, _button(text, lambda: self._open(uri)))
        return box

    def _spotify_login(self) -> Gtk.Box:
        box = self._section("login", "SPOTIFY SIGN-IN",
                            "Shows your playlists and followed artists. Opens your browser; "
                            "you have three minutes to approve. Needs the app keys above.")
        self.btn_login = _button("Sign in", self.login)
        self.btn_logout = _button("Sign out", self.logout)
        self._buttons(box, self.btn_login, self.btn_logout)
        return box

    def _spotify_player(self) -> Gtk.Box:
        box = self._section("player", "SPOTIFY PLAYER",
                            "The part that makes the sound (go-librespot). It pairs once, "
                            "separately from the sign-in above, and needs Spotify Premium.")
        self._buttons(box, _button("Pairing page", lambda: self._open("https://spotify.com/pair")),
                      _button("Check again", self.check_player))
        return box

    # --- state ---

    def on_shown(self):
        self.refresh()
        self.check_player()

    def refresh(self):
        for svc in SERVICES:
            sid = svc["id"]
            state = in_use(sid)
            self.status[sid].set_text(STATUS[state])
            self.forget[sid].set_visible(state == "app")
            stored = accounts.get(sid)
            for (name, _hint, secret), val in zip(svc["fields"], stored or ("",) * len(svc["fields"])):
                # a stored secret is never read back onto the screen
                if not secret and stored and not self.entries[sid][name].get_text():
                    self.entries[sid][name].set_text(val)
        signed_in = spotify_auth.logged_in()
        self.status["login"].set_text("Signed in" if signed_in else "Not signed in")
        self.btn_login.set_label("Sign in again" if signed_in else "Sign in")
        self.btn_login.set_sensitive(spotify.client_id() is not None)
        self.btn_logout.set_visible(signed_in)

    def _announce(self, sid: str, text: str):
        self.refresh()
        self._changed()
        self.status[sid].set_text(text)

    # --- actions ---

    def save(self, sid: str):
        values = {n: e.get_text() for n, e in self.entries[sid].items()}
        self.status[sid].set_text("Checking…")

        def work():
            accounts.check(sid, values)
            accounts.save(sid, values)

        def done(_result, err):
            if err:
                self.status[sid].set_text(f"Not saved: {err}")
                return False
            for name, _hint, secret in next(s for s in SERVICES if s["id"] == sid)["fields"]:
                if secret:
                    self.entries[sid][name].set_text("")
            self._announce(sid, "Saved, and it works")
            return False

        self._run(work, done)

    def forget_keys(self, sid: str):
        accounts.forget(sid)
        for e in self.entries[sid].values():
            e.set_text("")
        self._announce(sid, "Forgotten. " + STATUS[in_use(sid)])

    def login(self):
        cid = spotify.client_id()
        if cid is None:
            return
        self.btn_login.set_sensitive(False)
        self.status["login"].set_text("Waiting for you to approve in the browser…")

        def browse(url):
            GLib.idle_add(lambda: self._open(url) and False)

        def done(_result, err):
            self.btn_login.set_sensitive(True)
            if err:
                self.status["login"].set_text(f"Not signed in: {err}")
            else:
                self._announce("login", "Signed in")
            return False

        self._run(lambda: spotify_auth.login(cid, spotify.redirect_port(),
                                             open_browser=browse, say=lambda _t: None), done)

    def logout(self):
        spotify_auth.clear()
        self._announce("login", "Signed out")

    def check_player(self):
        def done(result, err):
            self.status["player"].set_text(err or result)
            return False
        self._run(player_status, done)
