"""Einstiegspunkt der App."""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from .config import style_file
from .window import CalendarWindow

log = logging.getLogger(__name__)

APP_ID = "de.icloudcalendar.App"


class CalendarApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None

    def do_activate(self):
        if self.win is None:
            self.win = CalendarWindow(self)
            self._load_css()
        self.win.present()

    def _load_css(self):
        from gi.repository import Gdk, Gtk

        path = style_file()
        if not path.exists():
            return
        provider = Gtk.CssProvider()
        try:
            provider.load_from_file(Gio.File.new_for_path(str(path)))
        except GLib.Error:
            log.exception("Stylesheet konnte nicht geladen werden: %s", path)
            return
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = CalendarApp()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    sys.exit(main())
