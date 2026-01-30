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
from sqlch.core import player, library


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
        self._discover_results: dict[str, dict] = {}

    # ------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Library")
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

    # ------------------------------------------------------------
    # Library
    # ------------------------------------------------------------

    def refresh_library(self):
        self.library_view.clear()

        stations = library.list_stations()
        if not stations:
            return

        for st in stations:
            label = f"{st['id']}  {st['name']}"
            self.library_view.append(ListItem(Label(label)))

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

        options = []
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
                label += f" [{codec.upper()}]"
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
        self._with_selected_station(player.preview, "Previewing")

    def action_play(self):
        self._with_selected_station(
            lambda url, st: player.play_url(url, name=st.get("name")),
            "Playing",
        )

    def action_add(self):
        urls = list(self.results.selected)
        if not urls:
            self.set_status("Nothing selected.")
            return

        for url in urls:
            st = self._discover_results.get(url)
            if st:
                library.add_discovered_station(st)

        self.set_status(f"Added {len(urls)} station(s).")

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _with_selected_station(self, fn, verb):
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

    def set_status(self, msg: str):
        self.status.update(msg)


def main():
    SQLCH().run()


if __name__ == "__main__":
    main()
