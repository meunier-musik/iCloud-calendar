"""Monatsansicht im Stil von Apple Calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango

from ..model import Event
from ..storage import Storage
from .util import MONTHS_DE, WEEKDAYS_DE, clear_widget, hex_to_rgba, month_grid_days

MAX_PILLS = 4


class MonthView(Gtk.Box):
    def __init__(self, storage: Storage, on_open_event: Callable, on_create_event: Callable):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.storage = storage
        self.on_open_event = on_open_event
        self.on_create_event = on_create_event
        self.current: date = date.today()
        self.selected: date = date.today()
        self.hidden_calendars: set[str] = set()

        header = Gtk.Grid(column_homogeneous=True)
        header.set_margin_top(6)
        for i, name in enumerate(WEEKDAYS_DE):
            lbl = Gtk.Label(label=name)
            lbl.add_css_class("weekday-header")
            header.attach(lbl, i, 0, 1, 1)
        self.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        self.grid.add_css_class("month-grid")
        scroll.set_child(self.grid)
        self.append(scroll)

        self.refresh()

    # ---------- API ----------

    def set_date(self, day: date) -> None:
        self.current = day
        self.refresh()

    def set_hidden_calendars(self, hidden: set[str]) -> None:
        self.hidden_calendars = hidden
        self.refresh()

    def refresh(self) -> None:
        clear_widget(self.grid)
        year, month = self.current.year, self.current.month
        days = month_grid_days(year, month)
        today = date.today()
        events_by_day: dict[date, list[Event]] = {}
        start = datetime.combine(days[0], datetime.min.time())
        end = datetime.combine(days[-1] + timedelta(days=1), datetime.min.time())
        for ev in self.storage.get_events_between(start, end):
            if ev.calendar_uid in self.hidden_calendars:
                continue
            for d in days:
                if ev.occurs_on(d):
                    events_by_day.setdefault(d, []).append(ev)

        for idx, day in enumerate(days):
            row, col = divmod(idx, 7)
            self.grid.attach(self._build_cell(day, month, today, events_by_day.get(day, [])), col, row + 1, 1, 1)

    @property
    def title(self) -> str:
        return f"{MONTHS_DE[self.current.month - 1]} {self.current.year}"

    # ---------- Aufbau ----------

    def _build_cell(self, day: date, month: int, today: date, events: list[Event]) -> Gtk.Widget:
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        cell.add_css_class("month-cell")
        if day.month != month:
            cell.add_css_class("other-month")
        if day == self.selected:
            cell.add_css_class("selected")

        num = Gtk.Label(label=str(day.day), halign=Gtk.Align.END)
        num.add_css_class("day-number")
        if day == today:
            num.add_css_class("today")
        box_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        sep = Gtk.Box(hexpand=True)
        box_top.append(sep)
        box_top.append(num)
        cell.append(box_top)

        for ev in events[:MAX_PILLS]:
            pill = Gtk.Label(label=ev.summary or "(Ohne Titel)")
            pill.add_css_class("event-pill")
            pill.set_ellipsize(Pango.EllipsizeMode.END)
            pill.set_halign(Gtk.Align.FILL)
            pill.set_tooltip_text(f"{ev.summary}\n{ev.start_local.strftime('%H:%M') if not ev.all_day else 'Ganztägig'}")
            cell.append(pill)
            self._apply_color(pill, ev)
        if len(events) > MAX_PILLS:
            more = Gtk.Label(label=f"+{len(events) - MAX_PILLS} weitere", halign=Gtk.Align.START)
            more.add_css_class("more-label")
            cell.append(more)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_cell_clicked, day, events)
        cell.add_controller(click)
        return cell

    def _apply_color(self, pill: Gtk.Label, ev: Event) -> None:
        cal = self.storage.get_calendar(ev.calendar_uid)
        color = cal.color if cal else "#007AFF"
        pill.set_markup(
            f'<span background="{color}" foreground="#FFFFFF"> {escape(ev.summary or "(Ohne Titel)")} </span>'
        )

    def _on_cell_clicked(self, gesture, n_press, x, y, day: date, events: list[Event]):
        self.selected = day
        self.refresh()
        self._show_day_popover(gesture.get_widget(), day, events)

    def _show_day_popover(self, widget, day: date, events: list[Event]):
        pop = Gtk.Popover()
        pop.add_css_class("event-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)

        head = Gtk.Label(label=day.strftime("%A, %d. %B %Y"))
        head.add_css_class("popover-title")
        box.append(head)

        if events:
            for ev in sorted(events, key=lambda e: (e.all_day is False, e.start_local)):
                row = Gtk.Button()
                row.set_has_frame(False)
                inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                dot = Gtk.Box()
                dot.add_css_class("cal-dot")
                dot.set_size_request(10, 10)
                cal = self.storage.get_calendar(ev.calendar_uid)
                self._color_widget(dot, cal.color if cal else "#007AFF")
                inner.append(dot)
                text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                t = Gtk.Label(label=ev.summary or "(Ohne Titel)", halign=Gtk.Align.START)
                t.add_css_class("popover-title")
                text.append(t)
                when = "Ganztägig" if ev.all_day else f"{ev.start_local.strftime('%H:%M')} – {ev.end_local.strftime('%H:%M')}"
                tl = Gtk.Label(label=when, halign=Gtk.Align.START)
                tl.add_css_class("popover-time")
                text.append(tl)
                inner.append(text)
                row.set_child(inner)
                row.connect("clicked", lambda *_b, e=ev: (pop.popdown(), self.on_open_event(e)))
                box.append(row)
        else:
            empty = Gtk.Label(label="Keine Termine")
            empty.add_css_class("dim-label")
            box.append(empty)

        add = Gtk.Button(label="Neuer Termin …")
        add.add_css_class("pill")
        add.connect("clicked", lambda *_b: (pop.popdown(), self.on_create_event(day)))
        box.append(add)

        pop.set_child(box)
        pop.set_parent(widget)
        pop.popup()


def _color_widget(widget: Gtk.Widget, color: str) -> None:
    widget.add_css_class("cal-dot")
    ctx = widget.get_style_context()
    # Inline-Hintergrund über CSS-Klassen-Ersatz:
    widget.set_opacity(1.0)
    provider = Gtk.CssProvider()
    provider.load_from_data(f"* {{ background-color: {color}; }}".encode())
    ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
