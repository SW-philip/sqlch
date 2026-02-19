# sqlch/sqlch/tui/app.py

_CACHE_DIR = None

def _cache_dir():
    global _CACHE_DIR
    if _CACHE_DIR is None:
        import os
        from pathlib import Path
        base = os.environ.get("XDG_CACHE_HOME")
        if not base:
            base = str(Path.home() / ".cache")
        p = Path(base) / "sqlch"
        p.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR = p
    return _CACHE_DIR

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Input, ListView, ListItem, Label, SelectionList, Static
from textual.binding import Binding
from textual.reactive import reactive
from sqlch.core.discover import search as rb_search
from sqlch.core import player, library


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
    .now-playing {
        color: $success;
        text-style: italic;
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
        yield Label("", id="now-playing-label", classes="now-playing")
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
            status = player.status_string()
        except Exception:
            status = "stopped"
        self.query_one("#now-playing-label", Label).update(status)


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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield TransportBar()
                yield Label("Library", id="sidebar-label")
                self.library_view = ListView()
                yield self.library_view
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
        self.refresh_search()

    def refresh_search(self) -> None:
        q = (self.query or "").strip()
        if not q:
            self.results.set_options([])
            self._discover_results.clear()
            self.set_status("Ready.")
            return
        try:
            stations = rb_search(q, limit=20)
        except Exception as e:
            self.results.set_options([])
            self._discover_results.clear()
            self.set_status(f"Search failed: {e}")
            return
        options = []
        self._discover_results.clear()
        for st in stations:
            url = st.get("url")
            if not url:
                continue
            name = (st.get("name") or "Unknown").strip()
            codec   = st.get("codec")
            bitrate = st.get("bitrate")
            country = st.get("country")
            label = name
            if codec:   label += f" [{codec.upper()}]"
            if bitrate: label += f" {bitrate}k"
            if country: label += f" ({country})"
            options.append((label, url))
            self._discover_results[url] = st
        self.results.set_options(options)
        self.set_status(f"Results: {len(options)}")

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
