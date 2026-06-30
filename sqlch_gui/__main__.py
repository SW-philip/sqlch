"""Entrypoint hook execution binary for sqlch-gui."""

import sys
from gi.repository import Gtk
from . import library
from .ui.window import SqlchPopupWindow

class SqlchGuiApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.prepko.sqlch-gui")

    def do_activate(self):
        win = SqlchPopupWindow(self)
        win.present()

def main():
    # Sync and guarantee frequency mapping configuration arrays are healthy
    library.backfill_freqs()
    
    app = SqlchGuiApp()
    sys.exit(app.run(sys.argv))

if __name__ == "__main__":
    main()