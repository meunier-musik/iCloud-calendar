"""Datenmodell für Kalender und Termine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from dateutil import tz as dateutil_tz
from icalendar import Calendar as ICalendar
from icalendar import Event as IEvent

LOCAL_TZ = dateutil_tz.tzlocal()
UTC = dateutil_tz.UTC


def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def new_uid() -> str:
    return f"{uuid.uuid4()}@icloud-calendar"


@dataclass
class CalendarInfo:
    """Ein Kalender (entspricht einem iCloud-Kalender)."""

    uid: str
    name: str
    color: str = "#FF3B30"
    href: str = ""
    readonly: bool = False

    def to_row(self) -> dict:
        return {
            "uid": self.uid,
            "name": self.name,
            "color": self.color,
            "href": self.href,
            "readonly": int(self.readonly),
        }

    @classmethod
    def from_row(cls, row) -> "CalendarInfo":
        return cls(
            uid=row["uid"],
            name=row["name"],
            color=row["color"],
            href=row["href"],
            readonly=bool(row["readonly"]),
        )


@dataclass
class Event:
    """Ein Termin."""

    uid: str = field(default_factory=new_uid)
    calendar_uid: str = ""
    href: str = ""
    etag: str = ""
    summary: str = ""
    location: str = ""
    description: str = ""
    start: datetime = field(default_factory=lambda: datetime.now(LOCAL_TZ).replace(minute=0, second=0, microsecond=0))
    end: datetime = field(default_factory=lambda: datetime.now(LOCAL_TZ).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    all_day: bool = False
    ics: str = ""

    @property
    def start_local(self) -> datetime:
        return _to_local(self.start)

    @property
    def end_local(self) -> datetime:
        return _to_local(self.end)

    @property
    def start_date(self) -> date:
        return self.start_local.date()

    @property
    def end_date(self) -> date:
        return self.end_local.date()

    def spans_days(self) -> bool:
        return self.all_day and (self.end_date - self.start_date) >= timedelta(days=1)

    def occurs_on(self, day: date) -> bool:
        if self.all_day:
            return self.start_date <= day <= self.end_date - timedelta(days=1)
        return self.start_date <= day <= self.end_date

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and self.end > start

    def to_ics(self) -> str:
        """Erzeugt eine VCALENDAR-Repräsentation dieses Termins."""
        ev = IEvent()
        ev.add("uid", self.uid)
        ev.add("summary", self.summary)
        if self.location:
            ev.add("location", self.location)
        if self.description:
            ev.add("description", self.description)
        if self.all_day:
            ev.add("dtstart", self.start_local.date())
            end_day = self.end_local.date()
            if self.end_local.time() == datetime.min.time() and self.end_local.date() > self.start_local.date():
                end_day = self.end_date  # DTEND ist exklusiv bei Ganztages-Terminen
            ev.add("dtend", end_day)
        else:
            ev.add("dtstart", self.start_local)
            ev.add("dtend", self.end_local)
        ev.add("dtstamp", datetime.now(UTC))
        cal = ICalendar()
        cal.add("prodid", "-//icloud-calendar//DE")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add_component(ev)
        return cal.to_ical().decode("utf-8")

    @classmethod
    def from_ics(cls, ics: str, calendar_uid: str = "", href: str = "", etag: str = "") -> list["Event"]:
        """Parst eine VCALENDAR-Datei (kann mehrere VEVENTs enthalten)."""
        try:
            cal = ICalendar.from_ical(ics)
        except ValueError:
            return []
        events = []
        for comp in cal.walk("VEVENT"):
            uid = str(comp.get("uid", new_uid()))
            dtstart = comp.get("dtstart")
            dtend = comp.get("dtend")
            if dtstart is None:
                continue
            start = dtstart.dt
            all_day = isinstance(start, date) and not isinstance(start, datetime)
            if all_day:
                start_dt = datetime.combine(start, datetime.min.time())
                if dtend is not None and isinstance(dtend.dt, date) and not isinstance(dtend.dt, datetime):
                    end_dt = datetime.combine(dtend.dt, datetime.min.time())
                else:
                    end_dt = start_dt + timedelta(days=1)
            else:
                start_dt = _to_local(start)
                if dtend is not None:
                    end_dt = _to_local(dtend.dt)
                elif comp.get("duration") is not None:
                    end_dt = start_dt + comp.get("duration").dt
                else:
                    end_dt = start_dt + timedelta(hours=1)
            if end_dt <= start_dt and not all_day:
                end_dt = start_dt + timedelta(minutes=15)
            events.append(
                cls(
                    uid=uid,
                    calendar_uid=calendar_uid,
                    href=href,
                    etag=etag,
                    summary=str(comp.get("summary", "")),
                    location=str(comp.get("location", "") or ""),
                    description=str(comp.get("description", "") or ""),
                    start=start_dt,
                    end=end_dt,
                    all_day=all_day,
                    ics=ics,
                )
            )
        return events


APPLE_CALENDAR_COLORS = [
    "#FF3B30",  # rot
    "#FF9500",  # orange
    "#FFCC00",  # gelb
    "#34C759",  # grün
    "#5AC8FA",  # hellblau
    "#007AFF",  # blau
    "#5856D6",  # indigo
    "#AF52DE",  # lila
    "#FF2D55",  # pink
    "#A2845E",  # braun
]
