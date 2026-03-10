# sqlch/sqlch/tui/app.py

import threading

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Input, ListView, ListItem, Label, SelectionList, Static
from textual.binding import Binding
from textual.reactive import reactive

from sqlch.core.discover import search as rb_search
from sqlch.core import player, library
from sqlch.core.player import now_playing_info


# Sqrlch mascot: a squirrel wearing headphones.
# Rendered dim at the foot of the sidebar as a watermark.
_MASCOT = (
    "   (\\  /)\n"
    "  =( o.o)=\n"
    "  =[|   |]=\n"
    "   (( u ))\n"
    "   /| db |\\\n"
    "  (_'----'_)\n"
    "  s q r l c h\n"
)


class MascotWidget(Static):
    DEFAULT_CSS = """
    MascotWidget {
        height: auto;
        color: $primary 25%;
        text-style: dim;
        text-align: center;
        padding: 1 0 0 0;
    }
    """

    def render(self) -> str:
        return _MASCOT


class TransportBar(Static):
    DEFAULT_CSS = """
    TransportBar {
        height: auto;
        border: round $accent;
        padding: 1 1;
        margin-bottom: 1;
    }
    .transport-title {
        color: $accent;
        text-style: bold;
    }
    .np-station {
        color: $success;
        text-style: bold;
        margin-top: 1;
    }
    .np-track {
        color: $success;
        text-style: italic;
        margin-bottom: 1;
    }
    .np-stopped {
        color: $text-muted;
        text-style: dim;
        margin-top: 1;
        margin-bottom: 1;
    }
    .transport-hint {
        color: $text-muted;
        text-style: dim;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Transport", classes="transport-title")
        yield Label("", id="np-station")
        yield Label("", id="np-track")
        yield Label("space  pause / resume",      classes="transport-hint")
        yield Label("s      stop",                classes="transport-hint")
        yield Label("enter  play highlighted",    classes="transport-hint")
        yield Label("p      preview (ducks 10s)", classes="transport-hint")
        yield Label("a      add to library",      classes="transport-hint")
        yield Label("r      refresh library",     classes="transport-hint")

    def on_mount(self) -> None:
        self.refresh_status()
        self.set_interval(2, self.refresh_status)

    def refresh_status(self) -> None:
        try:
            info = now_playing_info()
        except Exception:
            info = {"status": "stopped"}

        station_lbl = self.query_one("#np-station", Label)
        track_lbl   = self.query_one("#np-track", Label)

        if info["status"] == "stopped":
            station_lbl.set_classes("np-stopped")
            station_lbl.update("Not playing")
            track_lbl.update("")
            return

        station = info.get("station") or ""
        artist  = info.get("artist")
        track   = info.get("track")

        station_lbl.set_classes("np-station")
        station_lbl.update(f"\u266b {station}" if station else "\u266b")

        if track:
            track_lbl.set_classes("np-track")
            track_lbl.update(f"{artist} \u2014 {track}" if artist else track)
        else:
            track_lbl.set_classes("np-stopped")
            track_lbl.update("No track info")


class SQLCH(App):
    TITLE = "SQLCH"

    CSS = """
    Screen {
        background: $surface;
    }
    #sidebar {
        width: 32%;
        border: round $primary;
        padding: 1 1;
    }
    #sidebar-label {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    #main {
        width: 68%;
        border: round $primary;
        padding: 1 1;
    }
    #status {
        margin-top: 1;
        height: 3;
        border: round $accent;
        padding: 0 1;
        color: $success;
    }
    Input {
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("q",      "quit",            "Quit"),
        Binding("space",  "pause",           "Pause"),
        Binding("s",      "stop",            "Stop"),
        Binding("p",      "preview",         "Preview"),
        Binding("enter",  "play",            "Play"),
        Binding("a",      "add",             "Add Selected"),
        Binding("r",      "refresh_library", "Refresh Library"),
    ]

    query: reactive[str] = reactive("")

    def __init__(self):
        super().__init__()
        self._discover_results: dict[str, dict] = {}
        self._search_timer: threading.Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield TransportBar()
                yield Label("Library", id="sidebar-label")
                self.library_view = ListView()
                yield self.library_view
                yield MascotWidget()
            with Vertical(id="main"):
                yield Label("Discover (RadioBrowser)")
                self.search = Input(placeholder="Search RadioBrowser…")
                yield self.search
                self.results = SelectionList()
                yield self.results
                self.status = Label("Ready.", id="status")
                yield self.status
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_library()

    def refresh_library(self) -> None:
        self.library_view.clear()
        stations = library.list_stations()
        if not stations:
            return
        for st in stations:
            self.library_view.append(ListItem(Label(f"{st['id']}  {st['name']}")))

    def action_refresh_library(self) -> None:
        self.refresh_library()
        self.set_status("Library refreshed.")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is not self.search:
            return
        self.query = event.value

        if self._search_timer:
            self._search_timer.cancel()

        q = (self.query or "").strip()
        if not q:
            self.results.set_options([])
            self._discover_results.clear()
            self.set_status("Ready.")
            return

        self.set_status("Searching…")
        self._search_timer = threading.Timer(0.6, self._search_in_thread, args=(q,))
        self._search_timer.daemon = True
        self._search_timer.start()

    def _search_in_thread(self, q: str) -> None:
        try:
            stations = rb_search(q, limit=20)
        except Exception as e:
            self.call_from_thread(self.set_status, f"Search failed: {e}")
            return

        options = []
        results: dict[str, dict] = {}
        for st in stations:
            url = st.get("url")
            if not url:
                continue
            name    = (st.get("name") or "Unknown").strip()
            codec   = st.get("codec")
            bitrate = st.get("bitrate")
            country = st.get("country")
            label = name
            if codec:   label += f" [{codec.upper()}]"
            if bitrate: label += f" {bitrate}k"
            if country: label += f" ({country})"
            options.append((label, url))
            results[url] = st

        def _apply():
            self._discover_results = results
            self.results.set_options(options)
            self.set_status(f"Results: {len(options)}")

        self.call_from_thread(_apply)

    # ── transport ─────────────────────────────────────────────────────────────

    def action_pause(self) -> None:
        player.pause()
        self.set_status("Paused / resumed.")

    def action_stop(self) -> None:
        player.stop()
        self.set_status("Stopped.")

    def action_preview(self) -> None:
        idx = self.results.highlighted
        if idx is None or idx < 0:
            self.set_status("Highlight a search result to preview.")
            return
        try:
            url = list(self._discover_results)[idx]
        except IndexError:
            self.set_status("Selection out of range.")
            return
        st = self._discover_results.get(url)
        name = st.get("name", "Unknown") if st else "Unknown"
        currently = player.current()
        player.preview(url, duration=10)
        if currently:
            self.set_status(f"Ducking & previewing (10s): {name}")
        else:
            self.set_status(f"Previewing (10s): {name}")

    def action_play(self) -> None:
        self._with_selected_station(
            lambda url, st: player.play_station(st),
            "Playing",
        )

    def action_add(self) -> None:
        urls = list(self.results.selected)
        if not urls:
            self.set_status("Nothing selected.")
            return
        for url in urls:
            st = self._discover_results.get(url)
            if st:
                library.add_discovered_station(st)
        self.set_status(f"Added {len(urls)} station(s).")

    def _with_selected_station(self, fn, verb: str) -> None:
        idx = self.results.highlighted
        if idx is None or idx < 0:
            self.set_status("No result highlighted.")
            return
        try:
            url = list(self._discover_results)[idx]
        except IndexError:
            self.set_status("Selection out of range.")
            return
        st = self._discover_results.get(url)
        if not st:
            self.set_status("Internal error.")
            return
        fn(url, st)
        self.set_status(f"{verb}: {st.get('name', 'Unknown')}")

    def set_status(self, msg: str) -> None:
        self.status.update(msg)


def main():
    SQLCH().run()


if __name__ == "__main__":
    main()
