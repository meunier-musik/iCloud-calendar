"""Jahresansicht: 12 Mini-Monate im Apple-Stil."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, PangoCairo

from ..model import Event
from ..storage import Storage
from .util import MONTHS_DE, WEEKDAYS_DE, now_local


class MiniMonth(Gtk.DrawingArea):
    WIDTH, HEIGHT = 190, 170

    def __init__(self, year: int, month: int, storage: Storage, on_pick_day: Callable):
        super().__init__()
        self.year, self.month = year, month
        self.storage = storage
        self.on_pick_day = on_pick_day
        self.set_content_width(self.WIDTH)
        self.set_content_height(self.HEIGHT)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.add_controller(click)

    def _draw(self, area, cr, width, height):
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        today = date.today()

        title = f"{MONTHS_DE[self.month - 1]} {self.year}"
        layout = area.create_pango_layout("")
        layout.set_markup(f'<span size="9500" weight="bold">{title}</span>', -1)
        PangoCairo.show_layout(cr, layout, 8, 4)

        # Wochentage
        x0, y0 = 8, 28
        cw = (width - 16) / 7.0
        for i, wd in enumerate(WEEKDAYS_DE):
            lay = area.create_pango_layout("")
            lay.set_markup(f'<span foreground="#8E8E93" size="7000">{wd}</span>', -1)
            lw, lh = lay.get_pixel_size()
            PangoCairo.show_layout(cr, lay, x0 + i * cw + (cw - lw) / 2, y0)

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(self.year, self.month)
        day_events = self._events_by_day()
        rh = (height - y0 - 14) / max(1, len(weeks))
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                cx = x0 + c * cw + cw / 2
                cy = y0 + 14 + r * rh + rh / 2
                other = day.month != self.month
                is_today = day == today
                color = "#FF3B30" if is_today else ("#C7C7CC" if other else "#1C1C1E")
                if is_today:
                    cr.set_source_rgb(1, 0.231, 0.188)
                    cr.arc(cx, cy, 8.5, 0, 2 * 3.14159265)
                    cr.fill()
                    color = "#FFFFFF"
                weight = "bold" if is_today else "normal"
                lay = area.create_pango_layout("")
                lay.set_markup(
                    f'<span foreground="{color}" size="8000" weight="{weight}">{day.day}</span>',
                    -1,
                )
                lw, lh = lay.get_pixel_size()
                PangoCairo.show_layout(cr, lay, cx - lw / 2, cy - lh / 2)
                if day in day_events and not other and not is_today:
                    cr.set_source_rgb(0.55, 0.55, 0.58)
                    cr.arc(cx, cy + 7.5, 1.6, 0, 2 * 3.14159265)
                    cr.fill()
        self._last_weeks = weeks

    def _events_by_day(self) -> set:
        first = date(self.year, self.month, 1)
        last = (date(self.year, self.month, calendar.monthrange(self.year, self.month)[1]))
        start = datetime.combine(first, datetime.min.time())
        end = datetime.combine(last + timedelta(days=1), datetime.min.time())
        days = set()
        for ev in self.storage.get_events_between(start, end):
            d = ev.start_date
            while d <= ev.end_date:
                if d.month == self.month:
                    days.add(d)
                d += timedelta(days=1)
        return days

    def _on_click(self, gesture, n_press, x, y):
        weeks = getattr(self, "_last_weeks", [])
        if not weeks:
            return
        x0, y0 = 8, 28
        cw = (self.get_allocated_width() - 16) / 7.0
        rh = (self.HEIGHT - y0 - 14) / max(1, len(weeks))
        c = int((x - x0) // cw)
        r = int((y - y0 - 14) // rh)
        if 0 <= r < len(weeks) and 0 <= c < 7:
            day = weeks[r][c]
            if day.month == self.month:
                self.on_pick_day(day)


class YearView(Gtk.ScrolledWindow):
    def __init__(self, storage: Storage, on_pick_day: Callable):
        super().__init__()
        self.storage = storage
        self.on_pick_day = on_pick_day
        self.current = date.today()
        self.grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True)
        self.grid.add_css_class("year-view")
        self.set_child(self.grid)
        self.refresh()

    def set_date(self, day: date) -> None:
        self.current = day
        self.refresh()

    @property
    def title(self) -> str:
        return str(self.current.year)

    def set_hidden_calendars(self, hidden: set[str]) -> None:
        self.refresh()

    def refresh(self) -> None:
        child = self.grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt
        for m in range(12):
            mini = MiniMonth(self.current.year, m + 1, self.storage, self.on_pick_day)
            self.grid.attach(mini, m % 4, m // 4, 1, 1)
