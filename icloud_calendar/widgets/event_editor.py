"""Termin-Editor (Erstellen / Bearbeiten / Löschen)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: F401

from ..model import LOCAL_TZ, Event
from ..storage import Storage


def _parse_time(text: str) -> Optional[time]:
    text = text.strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%H"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


class DateButton(Gtk.MenuButton):
    """Button, der ein Datum anzeigt und einen Kalender-Popover öffnet."""

    def __init__(self, day: date, on_change: Callable[[date], None]):
        super().__init__()
        self._on_change = on_change
        self._label = Gtk.Label(label=day.strftime("%a., %d. %b. %Y"))
        self.set_child(self._label)
        self._calendar = Gtk.Calendar()
        self._calendar.set_show_heading(False)
        self._calendar.connect("day-selected", self._on_day_selected)
        self._calendar.connect("next-month", lambda *_: self._keep_open())
        self._calendar.connect("prev-month", lambda *_: self._keep_open())
        pop = Gtk.Popover()
        pop.set_child(self._calendar)
        self.set_popover(pop)
        self.set_date(day)

    def _keep_open(self) -> None:
        self.popup()

    def set_date(self, day: date) -> None:
        self._day = day
        self._label.set_text(day.strftime("%a., %d. %b. %Y"))
        self._calendar.select_day(GLib.DateTime.new_from_unix_local(int(datetime(day.year, day.month, day.day).timestamp())))

    def get_date(self) -> date:
        return self._day

    def _on_day_selected(self, *_):
        gdt = self._calendar.get_date()
        day = date(gdt.get_year(), gdt.get_month(), gdt.get_day_of_month())
        if day != self._day:
            self._on_change(day)
            self._day = day
            self._label.set_text(day.strftime("%a., %d. %b. %Y"))


class EventEditor(Gtk.Window):
    """Modaler Dialog zum Bearbeiten eines Termins."""

    def __init__(
        self,
        parent: Gtk.Window,
        event: Event,
        calendars: list,
        on_save: Callable[[Event], None],
        on_delete: Optional[Callable[[Event], None]] = None,
    ):
        super().__init__(modal=True, transient_for=parent, destroy_with_parent=True)
        self.set_title("Termin bearbeiten" if on_delete else "Neuer Termin")
        self.set_default_size(420, -1)
        self.event = event
        self.calendars = calendars
        self.on_save = on_save
        self.on_delete_cb = on_delete
        self._deleted = False

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.add_css_class("flat")

        cancel_btn = Gtk.Button(label="Abbrechen")
        cancel_btn.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Sichern")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)

        if on_delete:
            del_btn = Gtk.Button(label="Löschen")
            del_btn.add_css_class("destructive-action")
            del_btn.connect("clicked", self._on_delete)
            header.pack_end(del_btn)

        main.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(20)
        content.set_margin_end(20)

        self.title_entry = Gtk.Entry()
        self.title_entry.set_text(event.summary)
        self.title_entry.set_placeholder_text("Titel")
        self.title_entry.add_css_class("editor-title")
        content.append(self.title_entry)

        self.location_entry = Gtk.Entry()
        self.location_entry.set_text(event.location)
        self.location_entry.set_placeholder_text("Ort")
        content.append(self.location_entry)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        content.append(grid)

        lbl = Gtk.Label(label="Ganztägig", halign=Gtk.Align.END)
        self.all_day_switch = Gtk.Switch(active=event.all_day, halign=Gtk.Align.START)
        self.all_day_switch.connect("notify::active", self._on_all_day_toggled)
        grid.attach(lbl, 0, 0, 1, 1)
        grid.attach(self.all_day_switch, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Von", halign=Gtk.Align.END), 0, 1, 1, 1)
        start_box = Gtk.Box(spacing=8, halign=Gtk.Align.START)
        self.start_date_btn = DateButton(event.start_local.date(), self._on_start_date_changed)
        self.start_time_entry = Gtk.Entry(width_chars=6, text=event.start_local.strftime("%H:%M"))
        self.start_time_entry.set_placeholder_text("HH:MM")
        start_box.append(self.start_date_btn)
        start_box.append(self.start_time_entry)
        grid.attach(start_box, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Bis", halign=Gtk.Align.END), 0, 2, 1, 1)
        end_box = Gtk.Box(spacing=8, halign=Gtk.Align.START)
        self.end_date_btn = DateButton(event.end_local.date(), self._on_end_date_changed)
        self.end_time_entry = Gtk.Entry(width_chars=6, text=event.end_local.strftime("%H:%M"))
        self.end_time_entry.set_placeholder_text("HH:MM")
        end_box.append(self.end_date_btn)
        end_box.append(self.end_time_entry)
        grid.attach(end_box, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Kalender", halign=Gtk.Align.END), 0, 3, 1, 1)
        writable = [c for c in calendars if not c.readonly] or calendars
        strings = [c.name for c in writable]
        self.cal_drop = Gtk.DropDown.new_from_strings(strings)
        idx = 0
        for i, c in enumerate(writable):
            if c.uid == event.calendar_uid:
                idx = i
                break
        self.cal_drop.set_selected(idx)
        grid.attach(self.cal_drop, 1, 3, 1, 1)

        notes_lbl = Gtk.Label(label="Notizen", halign=Gtk.Align.START, valign=Gtk.Align.START)
        self.notes_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.notes_view.get_buffer().set_text(event.description)
        self.notes_view.set_size_request(-1, 80)
        frame = Gtk.Frame()
        frame.set_child(self.notes_view)
        grid.attach(notes_lbl, 0, 4, 1, 1)
        grid.attach(frame, 1, 4, 1, 1)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(content)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main.append(scroll)
        self.set_child(main)
        self._apply_all_day_visibility()

    # ---------- Verhalten ----------

    def _on_all_day_toggled(self, *_):
        self._apply_all_day_visibility()

    def _apply_all_day_visibility(self):
        hide = self.all_day_switch.get_active()
        self.start_time_entry.set_visible(not hide)
        self.end_time_entry.set_visible(not hide)

    def _on_start_date_changed(self, day: date):
        if self.end_date_btn.get_date() < day:
            self.end_date_btn.set_date(day + timedelta(days=1 if self.all_day_switch.get_active() else 0))

    def _on_end_date_changed(self, day: date):
        if day < self.start_date_btn.get_date():
            self.end_date_btn.set_date(self.start_date_btn.get_date())

    def _on_delete(self, *_):
        self._deleted = True
        if self.on_delete_cb:
            self.on_delete_cb(self.event)
        self.close()

    def _on_save(self, *_):
        ev = self._collect()
        if ev is None:
            return
        self.on_save(ev)
        self.close()

    def _collect(self) -> Optional[Event]:
        ev = self.event
        ev.summary = self.title_entry.get_text().strip() or "Ohne Titel"
        ev.location = self.location_entry.get_text().strip()
        buf = self.notes_view.get_buffer()
        ev.description = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        ev.all_day = self.all_day_switch.get_active()
        cal = self.calendars[self.cal_drop.get_selected()] if self.calendars else None
        if cal is not None:
            ev.calendar_uid = cal.uid

        start_day = self.start_date_btn.get_date()
        end_day = self.end_date_btn.get_date()
        if ev.all_day:
            ev.start = datetime.combine(start_day, time.min)
            ev.end = datetime.combine(max(end_day, start_day + timedelta(days=1)), time.min)
        else:
            t1 = _parse_time(self.start_time_entry.get_text()) or time(9, 0)
            t2 = _parse_time(self.end_time_entry.get_text()) or time(10, 0)
            start = datetime.combine(start_day, t1, tzinfo=LOCAL_TZ)
            end = datetime.combine(end_day, t2, tzinfo=LOCAL_TZ)
            if end <= start:
                end = start + timedelta(hours=1)
            ev.start, ev.end = start, end
        return ev
