#!/usr/bin/env python3
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Input,
    ListView,
    ListItem,
    Label,
    SelectionList,
)
from textual.binding import Binding
from textual.reactive import reactive

from sqlch.core.discover import search as rb_search
from sqlch.core import player


# ---- temporary library stub (wire later) ----
def list_library_stub():
    return [
        ("wxpn", "WXPN"),
        ("xponential", "XPONENTIAL"),
        ("ynot", "YNOT"),
    ]
# --------------------------------------------


class SQLCH(App):
    TITLE = "SQLCH"

    CSS = """
    Screen {
        background: black;
    }
    #sidebar {
        width: 30%;
        border: round white;
        padding: 1 1;
    }
    #main {
        width: 70%;
        border: round white;
        padding: 1 1;
    }
    #status {
        margin-top: 1;
        height: 3;
        border: round white;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "preview", "Preview"),
        Binding("enter", "play", "Play"),
        Binding("a", "add", "Add Selected"),
        Binding("s", "stop", "Stop"),
        Binding("r", "refresh_library", "Refresh Library"),
    ]

    query: reactive[str] = reactive("")

    def __init__(self):
        super().__init__()
        # url -> station dict
        self._discover_results: dict[str, dict] = {}

    # ------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Library")
                self.library = ListView()
                yield self.library

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

    # ------------------------------------------------------------
    # Library (stub)
    # ------------------------------------------------------------

    def refresh_library(self):
        self.library.clear()
        for slug, name in list_library_stub():
            self.library.append(ListItem(Label(f"{slug}  {name}")))

    def action_refresh_library(self):
        self.refresh_library()
        self.set_status("Library refreshed.")

    # ------------------------------------------------------------
    # Discover / Search
    # ------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is not self.search:
            return

        self.query = event.value
        self.refresh_search()

    def refresh_search(self):
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

        options: list[tuple[str, str]] = []
        self._discover_results.clear()

        for st in stations:
            url = st.get("url")
            if not url:
                continue

            name = (st.get("name") or "Unknown").strip()
            codec = st.get("codec")
            bitrate = st.get("bitrate")
            country = st.get("country")

            label = name
            if codec:
                label += f" [{str(codec).upper()}]"
            if bitrate:
                label += f" {bitrate}k"
            if country:
                label += f" ({country})"

            options.append((label, url))
            self._discover_results[url] = st

        self.results.set_options(options)
        self.set_status(f"Results: {len(options)}")

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------

    def action_stop(self):
        player.stop()
        self.set_status("Stopped.")

    def action_preview(self):
        idx = self.results.highlighted
        if idx is None or idx < 0:
            self.set_status("No result highlighted.")
            return

        urls = list(self._discover_results)
        try:
            url = urls[idx]
        except IndexError:
            self.set_status("Selection out of range.")
            return

        st = self._discover_results.get(url)
        if not st:
            self.set_status("Internal error: missing station data.")
            return

        name = st.get("name") or "Unknown"
        player.preview(url)
        self.set_status(f"Previewing: {name}")


    def action_play(self):
        idx = self.results.highlighted
        if idx is None or idx < 0:
            self.set_status("No result highlighted.")
            return

        urls = list(self._discover_results)
        try:
            url = urls[idx]
        except IndexError:
            self.set_status("Selection out of range.")
            return

        st = self._discover_results.get(url)
        if not st:
            self.set_status("Internal error: missing station data.")
            return

        name = st.get("name") or "Unknown"

        try:
            player.play_url(url, name=name)
            self.set_status(f"Playing: {name}")
        except AttributeError:
            player.preview(url)
            self.set_status(f"(Fallback) Playing: {name}")


    def action_add(self):
        urls = list(self.results.selected)
        if not urls:
            self.set_status("Nothing selected.")
            return

        for url in urls:
            st = self._discover_results.get(url)
            if not st:
                continue
            print(f"[ADD] {st.get('name', 'Unknown')} → {url}")
            # TODO: library.add_discovered_station(st)

        self.set_status(f"Queued add: {len(urls)} station(s).")

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def set_status(self, msg: str):
        self.status.update(msg)


if __name__ == "__main__":
    SQLCH().run()
