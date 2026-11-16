"""Gemeinsame Helfer für alle Ansichten."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: F401

from ..model import Event

WEEKDAYS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    if not rgba.parse(hex_color):
        rgba.parse("#007AFF")
    rgba.alpha = alpha
    return rgba


def start_of_week(day: date) -> date:
    """Wochenstart am Montag (wie im deutschen Apple Calendar)."""
    return day - timedelta(days=day.weekday())


def month_grid_days(year: int, month: int) -> list[date]:
    """42 Tage (6 Wochen), die die Monatsansicht füllen."""
    first = date(year, month, 1)
    start = start_of_week(first)
    return [start + timedelta(days=i) for i in range(42)]


def clear_widget(widget: Gtk.Widget) -> None:
    child = widget.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        widget.remove(child)
        child = nxt


def split_events(day_events: Iterable[Event]) -> tuple[list[Event], list[Event]]:
    """Teilt Termine in Ganztages- und zeitgebundene Termine."""
    all_day, timed = [], []
    for ev in day_events:
        if ev.all_day:
            all_day.append(ev)
        else:
            timed.append(ev)
    timed.sort(key=lambda e: (e.start_local, e.end_local))
    all_day.sort(key=lambda e: (e.start_local, e.summary))
    return all_day, timed


def format_time_range(ev: Event) -> str:
    s = ev.start_local.strftime("%H:%M")
    e = ev.end_local.strftime("%H:%M")
    return f"{s} – {e}"


def now_local() -> datetime:
    from ..model import LOCAL_TZ

    return datetime.now(LOCAL_TZ)
