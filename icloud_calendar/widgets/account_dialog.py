"""Dialog zur Eingabe der iCloud-Zugangsdaten."""

from __future__ import annotations

from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from ..sync.caldav_client import ICloudClient


class AccountDialog(Gtk.Window):
    """Erstkonfiguration: Apple-ID + App-spezifisches Passwort."""

    def __init__(self, parent: Optional[Gtk.Window], on_connect: Callable[[str, str], None]):
        super().__init__(modal=True, transient_for=parent, destroy_with_parent=True)
        self.set_title("iCloud-Konto")
        self.set_default_size(440, -1)
        self.on_connect = on_connect

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.add_css_class("flat")
        main.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(6)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        info = Gtk.Label(wrap=True, xalign=0)
        info.set_markup(
            "Melden Sie sich mit Ihrer <b>Apple-ID</b> an. iCloud verlangt ein "
            "<b>App-spezifisches Passwort</b> (nicht Ihr normales Apple-Passwort):\n\n"
            "1. <a href=\"https://appleid.apple.com\">appleid.apple.com</a> öffnen und anmelden\n"
            "2. <i>Anmelden und Sicherheit → App-spezifische Passwörter</i>\n"
            "3. Passwort erstellen und hier eintragen"
        )
        info.add_css_class("dim-label")
        content.append(info)

        self.user_entry = Gtk.Entry()
        self.user_entry.set_placeholder_text("Apple-ID (z. B. name@icloud.com)")
        content.append(self.user_entry)

        self.pass_entry = Gtk.PasswordEntry()
        self.pass_entry.set_placeholder_text("App-spezifisches Passwort")
        self.pass_entry.set_show_peek_icon(True)
        content.append(self.pass_entry)

        self.error_label = Gtk.Label(wrap=True, xalign=0)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)
        content.append(self.error_label)

        btn = Gtk.Button(label="Verbinden")
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.END)
        btn.connect("clicked", self._on_connect)
        content.append(btn)

        main.append(content)
        self.set_child(main)

    def _on_connect(self, *_):
        user = self.user_entry.get_text().strip()
        pwd = self.pass_entry.get_text()
        if not user or not pwd:
            self._show_error("Bitte Apple-ID und App-Passwort eingeben.")
            return
        try:
            ICloudClient(user, pwd).test_connection()
        except Exception as e:
            self._show_error(str(e))
            return
        self.close()
        self.on_connect(user, pwd)

    def _show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
