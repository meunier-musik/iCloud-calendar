"""Lokaler SQLite-Cache für Kalender und Termine."""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from .model import LOCAL_TZ, CalendarInfo, Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS calendars (
    uid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#FF3B30',
    href TEXT NOT NULL DEFAULT '',
    readonly INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    uid TEXT NOT NULL,
    calendar_uid TEXT NOT NULL REFERENCES calendars(uid) ON DELETE CASCADE,
    href TEXT NOT NULL DEFAULT '',
    etag TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0,
    ics TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (uid, calendar_uid)
);

CREATE INDEX IF NOT EXISTS idx_events_start ON events(start);
CREATE INDEX IF NOT EXISTS idx_events_cal ON events(calendar_uid);
"""


def _dt_to_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Storage:
    """Persistenter lokaler Speicher (Offline-Cache)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------- Kalender ----------

    def upsert_calendar(self, cal: CalendarInfo) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO calendars (uid, name, color, href, readonly) VALUES (?,?,?,?,?) "
                "ON CONFLICT(uid) DO UPDATE SET name=excluded.name, color=excluded.color, "
                "href=excluded.href, readonly=excluded.readonly",
                (cal.uid, cal.name, cal.color, cal.href, int(cal.readonly)),
            )
            self._conn.commit()

    def get_calendars(self) -> list[CalendarInfo]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM calendars ORDER BY name").fetchall()
        return [CalendarInfo.from_row(r) for r in rows]

    def get_calendar(self, uid: str) -> Optional[CalendarInfo]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM calendars WHERE uid=?", (uid,)).fetchone()
        return CalendarInfo.from_row(row) if row else None

    def delete_calendar(self, uid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM calendars WHERE uid=?", (uid,))
            self._conn.commit()

    # ---------- Termine ----------

    def replace_calendar_events(self, calendar_uid: str, events: Iterable[Event]) -> None:
        """Ersetzt alle Termine eines Kalenders (nach vollständigem Sync)."""
        with self._lock:
            self._conn.execute("BEGIN")
            self._conn.execute("DELETE FROM events WHERE calendar_uid=?", (calendar_uid,))
            for ev in events:
                self._insert_event(ev)
            self._conn.commit()

    def _insert_event(self, ev: Event) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO events (uid, calendar_uid, href, etag, summary, location, "
            "description, start, end, all_day, ics) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                ev.uid,
                ev.calendar_uid,
                ev.href,
                ev.etag,
                ev.summary,
                ev.location,
                ev.description,
                _dt_to_str(ev.start),
                _dt_to_str(ev.end),
                int(ev.all_day),
                ev.ics,
            ),
        )

    def upsert_event(self, ev: Event) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            self._insert_event(ev)
            self._conn.commit()

    def delete_event(self, uid: str, calendar_uid: str = "") -> None:
        with self._lock:
            if calendar_uid:
                self._conn.execute(
                    "DELETE FROM events WHERE uid=? AND calendar_uid=?", (uid, calendar_uid)
                )
            else:
                self._conn.execute("DELETE FROM events WHERE uid=?", (uid,))
            self._conn.commit()

    def get_event(self, uid: str, calendar_uid: str = "") -> Optional[Event]:
        with self._lock:
            if calendar_uid:
                row = self._conn.execute(
                    "SELECT * FROM events WHERE uid=? AND calendar_uid=?", (uid, calendar_uid)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT * FROM events WHERE uid=? LIMIT 1", (uid,)).fetchone()
        return self._row_to_event(row) if row else None

    def get_events_between(self, start: datetime, end: datetime) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE end > ? AND start < ? ORDER BY start",
                (_dt_to_str(start), _dt_to_str(end)),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_events_on_day(self, day: date) -> list[Event]:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        return self.get_events_between(start, end)

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        return Event(
            uid=row["uid"],
            calendar_uid=row["calendar_uid"],
            href=row["href"],
            etag=row["etag"],
            summary=row["summary"],
            location=row["location"],
            description=row["description"],
            start=_str_to_dt(row["start"]),
            end=_str_to_dt(row["end"]),
            all_day=bool(row["all_day"]),
            ics=row["ics"],
        )
