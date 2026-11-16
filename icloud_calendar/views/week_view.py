"""Wochen- und Tagesansicht als Zeitraster (Custom-Drawing im Apple-Stil)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo

from ..model import Event
from ..storage import Storage
from .util import WEEKDAYS_DE, format_time_range, hex_to_rgba, now_local, start_of_week

GUTTER = 56
HOUR_H = 52
HEADER_H = 44
ALLDAY_H = 24
MIN_COL_W = 110


class WeekView(Gtk.Box):
    """Zeitansicht; `days` = 7 (Woche) oder 1 (Tag)."""

    def __init__(self, storage: Storage, on_open_event: Callable, on_create_event: Callable, days: int = 7):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("week-view")
        self.storage = storage
        self.on_open_event = on_open_event
        self.on_create_event = on_create_event
        self.num_days = days
        self.current: date = date.today()
        self.hidden_calendars: set[str] = set()
        self._rects: list[tuple[Event, float, float, float, float, bool]] = []

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self._draw)
        self.scroll.set_child(self.area)
        self.append(self.scroll)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.area.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self.area.add_controller(motion)

        self.refresh()

    # ---------- API ----------

    def set_date(self, day: date) -> None:
        self.current = day
        self.refresh()

    def set_hidden_calendars(self, hidden: set[str]) -> None:
        self.hidden_calendars = hidden
        self.refresh()

    @property
    def title(self) -> str:
        if self.num_days == 1:
            d = self.current
            wd = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][d.weekday()]
            return f"{wd}, {d.day}. {d.month}. {d.year}"
        s = start_of_week(self.current)
        e = s + timedelta(days=6)
        if s.month == e.month:
            return f"{s.day}. – {e.day}. {s.month}. {s.year}"
        if s.year == e.year:
            return f"{s.day}. {s.month}. – {e.day}. {e.month}. {s.year}"
        return f"{s.day}.{s.month}.{s.year} – {e.day}.{e.month}.{e.year}"

    def view_days(self) -> list[date]:
        if self.num_days == 1:
            return [self.current]
        s = start_of_week(self.current)
        return [s + timedelta(days=i) for i in range(7)]

    def refresh(self) -> None:
        days = self.view_days()
        start = datetime.combine(days[0], datetime.min.time())
        end = datetime.combine(days[-1] + timedelta(days=1), datetime.min.time())
        events = [
            ev
            for ev in self.storage.get_events_between(start, end)
            if ev.calendar_uid not in self.hidden_calendars
        ]
        self._events = events
        total_h = HEADER_H + 3 * ALLDAY_H + 24 * HOUR_H
        self.area.set_content_width(max(720, GUTTER + self.num_days * MIN_COL_W))
        self.area.set_content_height(total_h)
        self.area.queue_draw()

    # ---------- Zeichnen ----------

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        days = self.view_days()
        col_w = (width - GUTTER) / self.num_days
        all_day_events, timed_events = self._layout(days)
        allday_rows = max(1, self._max_lanes(days))

        top = HEADER_H
        band_h = allday_rows * ALLDAY_H + 6
        grid_top = top + band_h

        # Hintergrund
        cr.set_source_rgb(1, 1, 1)
        cr.paint()

        # Kopfzeile
        cr.set_source_rgb(0.984, 0.984, 0.992)
        cr.rectangle(0, 0, width, HEADER_H)
        cr.fill()
        cr.set_source_rgb(0.898, 0.898, 0.918)
        cr.set_line_width(1)
        cr.move_to(0, HEADER_H + 0.5)
        cr.line_to(width, HEADER_H + 0.5)
        cr.stroke()

        today = date.today()
        self._rects = []
        for i, day in enumerate(days):
            x = GUTTER + i * col_w
            if i > 0:
                cr.set_source_rgb(0.898, 0.898, 0.918)
                cr.move_to(x + 0.5, HEADER_H)
                cr.line_to(x + 0.5, height)
                cr.stroke()
            wd = WEEKDAYS_DE[day.weekday()]
            is_today = day == today
            color = "#FF3B30" if is_today else "#1C1C1E"
            layout = area.create_pango_layout("")
            layout.set_markup(
                f'<span foreground="{color}" size="9500" weight="bold">{wd}</span> '
                f'<span foreground="{color}" size="12500" weight="bold">{day.day}.</span>',
                -1,
            )
            lw, lh = layout.get_pixel_size()
            PangoCairo.show_layout(cr, layout, x + (col_w - lw) / 2, (HEADER_H - lh) / 2)

        # Ganztages-Band
        cr.set_source_rgb(0.965, 0.965, 0.973)
        cr.rectangle(0, top, GUTTER, band_h)
        cr.fill()
        lay = area.create_pango_layout("")
        lay.set_markup('<span foreground="#8E8E93" size="8000">Ganztägig</span>', -1)
        lw, lh = lay.get_pixel_size()
        PangoCairo.show_layout(cr, lay, 8, top + (band_h - lh) / 2)

        cr.set_source_rgb(0.898, 0.898, 0.918)
        cr.move_to(0, grid_top + 0.5)
        cr.line_to(width, grid_top + 0.5)
        cr.stroke()

        for ev, lane, d0, d1 in all_day_events:
            i0 = days.index(d0)
            i1 = days.index(d1)
            x = GUTTER + i0 * col_w + 2
            y = top + lane * ALLDAY_H + 3
            w = (i1 - i0 + 1) * col_w - 4
            h = ALLDAY_H - 6
            color = self._event_color(ev)
            self._rounded_rect(cr, x, y, w, h, 5)
            cr.set_source_rgba(*_rgba_tuple(color))
            cr.fill()
            self._clip_text(cr, area, ev.summary or "(Ohne Titel)", x + 6, y + 1, w - 12, h, "#FFFFFF")
            self._rects.append((ev, x, y, w, h, True))

        # Stundenraster
        for hour in range(25):
            y = grid_top + hour * HOUR_H
            if hour < 24:
                cr.set_source_rgb(0.898, 0.898, 0.918)
                cr.set_line_width(1)
            else:
                cr.set_source_rgb(0.937, 0.937, 0.949)
                cr.set_line_width(0.5)
            cr.move_to(GUTTER, y + 0.5)
            cr.line_to(width, y + 0.5)
            cr.stroke()
            if hour < 24:
                cr.set_source_rgb(0.4, 0.4, 0.43)
                lay = area.create_pango_layout("")
                lay.set_markup(f'<span foreground="#8E8E93" size="8000">{hour:02d}:00</span>', -1)
                lw, lh = lay.get_pixel_size()
                PangoCairo.show_layout(cr, lay, GUTTER - lw - 8, y - lh / 2)
            if hour < 24:
                cr.set_source_rgb(0.949, 0.949, 0.961)
                cr.set_line_width(0.5)
                yh = y + HOUR_H / 2
                cr.move_to(GUTTER, yh + 0.5)
                cr.line_to(width, yh + 0.5)
                cr.stroke()

        # Termine
        for ev, lane, d0, d1 in timed_events:
            i = days.index(d0)
            col_start = GUTTER + i * col_w
            col_end = col_start + col_w
            x, y, w, h = self._event_rect(ev, col_start, col_end, grid_top, lane, d0, d1, days)
            color = self._event_color(ev)
            self._rounded_rect(cr, x, y, w, h, 6)
            cr.set_source_rgba(*_rgba_tuple(color, 0.92))
            cr.fill()
            time_txt = "" if ev.all_day else format_time_range(ev)
            label = (time_txt + "\n" if time_txt else "") + (ev.summary or "(Ohne Titel)")
            self._clip_text(cr, area, label, x + 5, y + 2, w - 10, h - 4, "#FFFFFF", small=True)
            self._rects.append((ev, x, y, w, h, False))

        # Jetzt-Linie
        now = now_local()
        if now.date() in days:
            i = days.index(now.date())
            y = grid_top + (now.hour + now.minute / 60) * HOUR_H
            x0 = GUTTER + i * col_w
            cr.set_source_rgb(1, 0.231, 0.188)
            cr.set_line_width(1.5)
            cr.move_to(x0, y)
            cr.line_to(width, y)
            cr.stroke()
            cr.arc(x0, y, 4, 0, 2 * math.pi)
            cr.fill()

    # ---------- Layout-Helfer ----------

    def _layout(self, days: list[date]):
        """Ordnet Termine in Spuren (Lanes) pro Tag an."""
        all_day, timed = [], []
        for ev in self._events:
            d0 = max(ev.start_date, days[0])
            d1 = min(ev.end_local.date() - timedelta(days=1) if ev.all_day else ev.end_date, days[-1])
            if d1 < d0:
                d1 = d0
            if ev.all_day:
                all_day.append((ev, 0, d0, d1))
            else:
                timed.append((ev, 0, d0, d1))

        # Lane-Belegung für Ganztages-Termine
        all_day.sort(key=lambda t: (t[2], t[3]))
        lane_ends: list[date] = []
        for idx, item in enumerate(all_day):
            ev, _, d0, d1 = item
            lane = 0
            while lane < len(lane_ends) and lane_ends[lane] >= d0:
                lane += 1
            if lane == len(lane_ends):
                lane_ends.append(d1)
            else:
                lane_ends[lane] = d1
            all_day[idx] = (ev, lane, d0, d1)

        # Lane-Belegung für zeitgebundene Termine (pro Tag, Überlappung)
        timed.sort(key=lambda t: (t[2], t[0].start_local, t[0].end_local))
        by_day: dict[date, list] = {}
        for item in timed:
            by_day.setdefault(item[2], []).append(item)
        for day, items in by_day.items():
            lane_ends: list[datetime] = []
            for idx, (ev, _, d0, d1) in enumerate(items):
                lane = 0
                while lane < len(lane_ends) and lane_ends[lane] > ev.start_local:
                    lane += 1
                if lane == len(lane_ends):
                    lane_ends.append(ev.end_local)
                else:
                    lane_ends[lane] = ev.end_local
                items[idx] = (ev, lane, d0, d1)
        return all_day, timed

    def _max_lanes(self, days: list[date]) -> int:
        all_day, _ = self._layout(days)
        lanes = [lane for _, lane, _, _ in all_day]
        return (max(lanes) + 1) if lanes else 1

    def _event_rect(self, ev: Event, col_x: float, col_end: float, grid_top: float, lane: int,
                    d0: date, d1: date, days: list[date]) -> tuple[float, float, float, float]:
        col_w = col_end - col_x
        s = ev.start_local
        e = ev.end_local
        if s.date() < d0:
            s = datetime.combine(d0, datetime.min.time(), tzinfo=s.tzinfo)
        if e.date() > d1:
            e = datetime.combine(d1 + timedelta(days=1), datetime.min.time(), tzinfo=e.tzinfo)
        y0 = grid_top + (s.hour + s.minute / 60 + s.second / 3600) * HOUR_H
        y1 = grid_top + (e.hour + e.minute / 60 + e.second / 3600) * HOUR_H
        y1 = max(y1, y0 + 16)
        x = col_x + 2 + lane * 6
        w = col_w - 4 - lane * 6
        return x, y0 + 1, w, (y1 - y0) - 2

    def _event_color(self, ev: Event) -> str:
        cal = self.storage.get_calendar(ev.calendar_uid)
        return cal.color if cal else "#007AFF"

    def _rounded_rect(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _clip_text(self, cr, area, text: str, x, y, w, h, color: str, small: bool = False):
        cr.save()
        cr.rectangle(x - 1, y - 1, w + 2, h + 2)
        cr.clip()
        lines = text.split("\n")
        yy = y
        for i, line in enumerate(lines):
            if yy > y + h:
                break
            layout = area.create_pango_layout("")
            size = 8000 if small else 9000
            weight = "normal" if (small and i == 0) else "bold"
            layout.set_markup(
                f'<span foreground="{color}" size="{size}" weight="{weight}">{_esc(line)}</span>', -1
            )
            layout.set_width(int(w * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            PangoCairo.show_layout(cr, layout, x, yy)
            _, lh = layout.get_pixel_size()
            yy += lh + 1
        cr.restore()

    # ---------- Interaktion ----------

    def _hit_test(self, x: float, y: float) -> tuple[Optional[Event], bool]:
        for ev, rx, ry, rw, rh, is_all_day in self._rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return ev, is_all_day
        return None, False

    def _on_motion(self, ctl, x, y):
        ev, _ = self._hit_test(x, y)
        self.area.set_cursor_from_name("pointer" if ev else "default")

    def _on_click(self, gesture, n_press, x, y):
        days = self.view_days()
        col_w = (self.area.get_allocated_width() - GUTTER) / self.num_days
        ev, is_all_day = self._hit_test(x, y)
        if ev is not None:
            self.on_open_event(ev)
            return
        width = self.area.get_allocated_width()
        allday_rows = max(1, self._max_lanes(days))
        band_h = allday_rows * ALLDAY_H + 6
        grid_top = HEADER_H + band_h
        if y < grid_top:
            idx = min(self.num_days - 1, max(0, int((x - GUTTER) / col_w)))
            self.on_create_event(days[idx], all_day=True)
            return
        if x < GUTTER:
            return
        idx = min(self.num_days - 1, max(0, int((x - GUTTER) / col_w)))
        minutes = (y - grid_top) / HOUR_H * 60
        minutes = min(23 * 60 + 30, round(minutes / 30) * 30)
        day = days[idx]
        start = datetime.combine(day, datetime.min.time(), tzinfo=now_local().tzinfo) + timedelta(minutes=int(minutes))
        self.on_create_event(start, all_day=False)


def _rgba_tuple(color: str, alpha: float = 1.0) -> tuple:
    c = Gdk.RGBA()
    if not c.parse(color):
        c.parse("#007AFF")
    return (c.red, c.green, c.blue, alpha)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
