"""Radio source pane: the station Library and worldwide Discover as two pills
inside one docked window. Each keeps its own search/filter and favorites."""

from gi.repository import Gtk

SECTIONS = (("library", "LIBRARY"), ("discover", "DISCOVER"))


class RadioPane(Gtk.Box):
    def __init__(self, library, discover):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._panels = {"library": library, "discover": discover}
        self._section = "library"
        self._shown = False

        pills = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        pills.set_margin_start(6)
        pills.set_margin_end(6)
        pills.set_margin_top(6)
        self._pills = {}
        for sid, title in SECTIONS:
            pill = Gtk.Button(label=title)
            pill.add_css_class("section-pill")
            pill.connect("clicked", lambda _b, s=sid: self.select(s))
            pills.append(pill)
            self._pills[sid] = pill
        self.append(pills)

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        for sid, _title in SECTIONS:
            self.stack.add_named(self._panels[sid], sid)
        self.append(self.stack)
        self._mark()

    @property
    def section(self) -> str:
        return self._section

    def _mark(self):
        self.stack.set_visible_child_name(self._section)
        for sid, pill in self._pills.items():
            if sid == self._section:
                pill.add_css_class("active")
            else:
                pill.remove_css_class("active")

    def select(self, sid: str):
        if sid not in self._panels or sid == self._section:
            return
        if self._shown and self._section == "library":
            self._panels["library"].abort_probes()
        self._section = sid
        self._mark()
        if self._shown and sid == "library":
            self._panels["library"].on_shown()

    def on_shown(self):
        self._shown = True
        if self._section == "library":
            self._panels["library"].on_shown()

    def on_hidden(self):
        self._shown = False
        self._panels["library"].abort_probes()
