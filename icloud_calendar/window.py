"""Hauptfenster der App."""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango

from .config import Config, db_file, get_config
from .model import LOCAL_TZ, CalendarInfo, Event
from .storage import Storage
from .sync.caldav_client import ICloudClient
from .sync.manager import SyncManager
from .views.month_view import MonthView
from .views.week_view import WeekView
from .views.year_view import YearView
from .widgets.account_dialog import AccountDialog
from .widgets.event_editor import EventEditor

LOCAL_CAL_UID = "local"
VIEW_NAMES = {"day": "Tag", "week": "Woche", "month": "Monat", "year": "Jahr"}


class CalendarWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self.set_title("Kalender")
        self.set_default_size(1100, 720)
        self.add_css_class("calendar-window")

        self.config: Config = get_config()
        self.storage = Storage(db_file())
        self._ensure_local_calendar()

        self.client: Optional[ICloudClient] = None
        if self.config.account_configured:
            self.client = ICloudClient(self.config.username, self.config.password)
        self.sync_manager = SyncManager(self.storage, self.client)

        self.hidden: set[str] = set(self.config.data.get("hidden", []))
        self._current = date.today()

        self._build_ui()
        self._install_actions(app)
        self.reload_sidebar()
        self._update_title()

        GLib.timeout_add(300, self._startup, priority=GLib.PRIORITY_DEFAULT)
        GLib.timeout_add_seconds(900, self._auto_sync)

    # ---------- Aufbau ----------

    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(root)

        header = Adw.HeaderBar()

        sidebar_btn = Gtk.ToggleButton()
        sidebar_btn.set_icon_name("sidebar-show-symbolic")
        sidebar_btn.set_active(True)
        sidebar_btn.connect("toggled", self._on_sidebar_toggled)
        header.pack_start(sidebar_btn)

        today_btn = Gtk.Button(label="Heute")
        today_btn.add_css_class("today-button")
        today_btn.connect("clicked", lambda *_: self.go_today())
        header.pack_start(today_btn)

        prev_btn = Gtk.Button()
        prev_btn.set_icon_name("go-previous-symbolic")
        prev_btn.connect("clicked", lambda *_: self.navigate(-1))
        header.pack_start(prev_btn)

        next_btn = Gtk.Button()
        next_btn.set_icon_name("go-next-symbolic")
        next_btn.connect("clicked", lambda *_: self.navigate(1))
        header.pack_start(next_btn)

        self.title_label = Gtk.Label()
        self.title_label.add_css_class("title-label")
        header.set_title_widget(self.title_label)

        self.sync_btn = Gtk.Button()
        self.sync_btn.set_icon_name("emblem-synchronizing-symbolic")
        self.sync_btn.set_tooltip_text("Mit iCloud synchronisieren")
        self.sync_btn.connect("clicked", lambda *_: self.start_sync())
        header.pack_end(self.sync_btn)

        add_btn = Gtk.Button()
        add_btn.set_icon_name("list-add-symbolic")
        add_btn.set_tooltip_text("Neuer Termin")
        add_btn.connect("clicked", lambda *_: self.new_event())
        header.pack_end(add_btn)

        switch_box = Gtk.Box(spacing=0)
        switch_box.add_css_class("linked")
        switch_box.add_css_class("view-switcher")
        self._view_buttons: dict[str, Gtk.ToggleButton] = {}
        for key in ("day", "week", "month", "year"):
            btn = Gtk.ToggleButton(label=VIEW_NAMES[key])
            btn.connect("toggled", self._on_view_toggled, key)
            self._view_buttons[key] = btn
            switch_box.append(btn)
        header.pack_end(switch_box)

        root.append(header)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.append(body)
        body.set_vexpand(True)

        # Seitenleiste
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=210)
        self.sidebar.add_css_class("sidebar")
        body.append(self.sidebar)

        side_title = Gtk.Label(label="iCloud", xalign=0)
        side_title.add_css_class("sidebar-title")
        self.sidebar.append(side_title)

        side_scroll = Gtk.ScrolledWindow()
        side_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_vexpand(True)
        self.cal_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.cal_list.add_css_class("navigation-sidebar")
        side_scroll.set_child(self.cal_list)
        self.sidebar.append(side_scroll)

        self.account_btn = Gtk.Button()
        self.account_btn.add_css_class("flat")
        self.account_btn.set_halign(Gtk.Align.FILL)
        self.account_btn.connect("clicked", self._on_account_clicked)
        self.sidebar.append(self.account_btn)

        # Ansichten
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        body.append(self.stack)

        self.month_view = MonthView(self.storage, self.open_event, self.create_event_at)
        self.week_view = WeekView(self.storage, self.open_event, self.create_event_at, days=7)
        self.day_view = WeekView(self.storage, self.open_event, self.create_event_at, days=1)
        self.year_view = YearView(self.storage, self._on_year_day_picked)
        self.views = {
            "day": self.day_view,
            "week": self.week_view,
            "month": self.month_view,
            "year": self.year_view,
        }
        for key, view in self.views.items():
            self.stack.add_named(view, key)
        self._view_buttons[self.config.view].set_active(True)

    def _install_actions(self, app: Adw.Application) -> None:
        actions = {
            "today": (["<Ctrl>t"], lambda *_: self.go_today()),
            "new-event": (["<Ctrl>n"], lambda *_: self.new_event()),
            "sync": (["<Ctrl>r"], lambda *_: self.start_sync()),
            "prev": (["<Ctrl>Left"], lambda *_: self.navigate(-1)),
            "next": (["<Ctrl>Right"], lambda *_: self.navigate(1)),
        }
        for i, name in enumerate(("day", "week", "month", "year")):
            actions[f"view-{name}"] = ([f"<Ctrl>{i + 1}"], self._make_view_action(name))
        for name, (accels, cb) in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            app.set_accels_for_action(f"win.{name}", accels)

    def _make_view_action(self, key: str):
        def _cb(*_):
            self._view_buttons[key].set_active(True)

        return _cb

    # ---------- Seitenleiste ----------

    def _ensure_local_calendar(self) -> None:
        if self.storage.get_calendar(LOCAL_CAL_UID) is None:
            self.storage.upsert_calendar(
                CalendarInfo(
                    uid=LOCAL_CAL_UID,
                    name="Lokal",
                    color="#8E8E93",
                    href="",
                    readonly=False,
                )
            )

    def reload_sidebar(self) -> None:
        child = self.cal_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.cal_list.remove(child)
            child = nxt

        for cal in self.storage.get_calendars():
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            check = Gtk.CheckButton(active=cal.uid not in self.hidden)
            check.connect("toggled", self._on_cal_visibility, cal.uid)
            dot = Gtk.Box()
            dot.add_css_class("cal-dot")
            dot.set_size_request(12, 12)
            dot.set_valign(Gtk.Align.CENTER)
            self._color_dot(dot, cal.color)
            name = Gtk.Label(label=cal.name, halign=Gtk.Align.START)
            name.add_css_class("cal-name")
            name.set_ellipsize(Pango.EllipsizeMode.END)
            box.append(check)
            box.append(dot)
            box.append(name)
            row.set_child(box)
            self.cal_list.append(row)

        if self.config.account_configured:
            self.account_btn.set_label(self.config.username)
        else:
            self.account_btn.set_label("iCloud-Konto einrichten …")

    def _color_dot(self, widget: Gtk.Widget, color: str) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(f"* {{ background-color: {color}; }}".encode())
        widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_cal_visibility(self, check: Gtk.CheckButton, uid: str) -> None:
        if check.get_active():
            self.hidden.discard(uid)
        else:
            self.hidden.add(uid)
        self.config.data["hidden"] = sorted(self.hidden)
        self.config.save()
        for view in self.views.values():
            view.set_hidden_calendars(self.hidden)

    def _on_account_clicked(self, *_):
        AccountDialog(self, self._on_account_connected).present()

    def _on_account_connected(self, username: str, password: str) -> None:
        self.config.set_account(username, password)
        self.client = ICloudClient(username, password)
        self.sync_manager.client = self.client
        self.reload_sidebar()
        self.start_sync()

    # ---------- Navigation / Ansichten ----------

    def _active_view_key(self) -> str:
        for key, btn in self._view_buttons.items():
            if btn.get_active():
                return key
        return "month"

    def _on_view_toggled(self, btn: Gtk.ToggleButton, key: str) -> None:
        if not btn.get_active() or self.stack.get_child_by_name(key) is None:
            return
        self.stack.set_visible_child_name(key)
        self.config.set_view(key)
        view = self.views[key]
        view.set_date(self._current)
        self._update_title()

    def _update_title(self) -> None:
        view = self.views[self._active_view_key()]
        self.title_label.set_text(view.title)

    def go_today(self) -> None:
        self._current = date.today()
        self._apply_current()

    def navigate(self, direction: int) -> None:
        key = self._active_view_key()
        if key == "day":
            self._current += timedelta(days=direction)
        elif key == "week":
            self._current += timedelta(weeks=direction)
        elif key == "month":
            month = self._current.month + direction
            year = self._current.year
            if month < 1:
                month, year = 12, year - 1
            elif month > 12:
                month, year = 1, year + 1
            self._current = date(year, month, min(self._current.day, 28))
        else:
            self._current = date(self._current.year + direction, self._current.month, 28)
        self._apply_current()

    def _apply_current(self) -> None:
        for view in self.views.values():
            view.set_date(self._current)
        self._update_title()

    def _on_year_day_picked(self, day: date) -> None:
        self._current = day
        self._view_buttons["day"].set_active(True)

    # ---------- Termine ----------

    def new_event(self) -> None:
        self.create_event_at(self._current)

    def create_event_at(self, when, all_day: bool = False) -> None:
        day = when.date() if isinstance(when, datetime) else when
        if all_day:
            ev = Event(
                calendar_uid=self._default_calendar_uid(),
                start=datetime.combine(day, datetime.min.time()),
                end=datetime.combine(day + timedelta(days=1), datetime.min.time()),
                all_day=True,
            )
        else:
            start = when if isinstance(when, datetime) else datetime.combine(
                day, datetime.min.time(), tzinfo=LOCAL_TZ
            ).replace(hour=9)
            if start.tzinfo is None:
                start = start.replace(tzinfo=LOCAL_TZ)
            ev = Event(
                calendar_uid=self._default_calendar_uid(),
                start=start,
                end=start + timedelta(hours=1),
            )
        self._open_editor(ev, is_new=True)

    def _default_calendar_uid(self) -> str:
        for cal in self.storage.get_calendars():
            if not cal.readonly and cal.uid not in self.hidden:
                return cal.uid
        return LOCAL_CAL_UID

    def open_event(self, ev: Event) -> None:
        self._open_editor(ev, is_new=False)

    def _open_editor(self, ev: Event, is_new: bool) -> None:
        calendars = self.storage.get_calendars()
        editor = EventEditor(
            self,
            ev,
            calendars,
            on_save=lambda e: self._save_event(e, is_new),
            on_delete=None if is_new else self._delete_event,
        )
        editor.present()

    def _save_event(self, ev: Event, is_new: bool) -> None:
        old = None if is_new else self.storage.get_event(ev.uid, ev.calendar_uid)
        old_cal_uid = old.calendar_uid if old else ev.calendar_uid

        def work():
            if is_new:
                self.sync_manager.create_event(ev)
            elif old_cal_uid != ev.calendar_uid:
                old_ev = self.storage.get_event(ev.uid, old_cal_uid)
                if old_ev:
                    self.sync_manager.delete_event(old_ev)
                self.sync_manager.create_event(ev)
            else:
                self.sync_manager.update_event(ev)

        self._run_async(
            work,
            lambda err: self._after_write(err, f"Termin „{ev.summary}“ gesichert."),
        )

    def _delete_event(self, ev: Event) -> None:
        self._run_async(
            lambda: self.sync_manager.delete_event(ev),
            lambda err: self._after_write(err, "Termin gelöscht."),
        )

    def _after_write(self, err: Optional[str], ok_msg: str) -> None:
        if err:
            self.show_toast(f"Fehler: {err}")
        else:
            self.show_toast(ok_msg)
        self.refresh_views()

    def refresh_views(self) -> None:
        for view in self.views.values():
            view.refresh()
        self.reload_sidebar()

    # ---------- Sync ----------

    def _startup(self) -> bool:
        if self.config.account_configured:
            self.start_sync()
        else:
            dlg = AccountDialog(self, self._on_account_connected)
            dlg.present()
        return False

    def _auto_sync(self) -> bool:
        if self.config.account_configured and not self.sync_manager.syncing:
            self.start_sync()
        return True

    def start_sync(self) -> None:
        if not self.config.account_configured:
            dlg = AccountDialog(self, self._on_account_connected)
            dlg.present()
            return
        if self.sync_manager.syncing:
            return
        self.sync_btn.set_sensitive(False)
        self.show_toast("Synchronisiere mit iCloud …")
        self.sync_manager.sync_async(
            on_done=lambda err: GLib.idle_add(self._sync_finished, err)
        )

    def _sync_finished(self, err: Optional[str]) -> bool:
        self.sync_btn.set_sensitive(True)
        if err:
            self.show_toast(f"Sync fehlgeschlagen: {err}")
        else:
            self.show_toast("Synchronisation abgeschlossen.")
        self.refresh_views()
        return False

    # ---------- Hilfsfunktionen ----------

    def show_toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)

    def _run_async(self, fn: Callable[[], None], on_done: Callable[[Optional[str]], None]) -> None:
        def work():
            err = None
            try:
                fn()
            except Exception as e:
                err = str(e)
            GLib.idle_add(self._call_on_done, on_done, err)

        threading.Thread(target=work, daemon=True, name="app-async").start()

    @staticmethod
    def _call_on_done(fn: Callable, err: Optional[str]) -> bool:
        fn(err)
        return False
