import json
from datetime import date, datetime, timedelta

import pytest

from icloud_calendar.model import LOCAL_TZ, CalendarInfo, Event


def aware(h=10, m=0, day=16):
    return datetime(2025, 1, day, h, m, tzinfo=LOCAL_TZ)


class TestEventIcsRoundTrip:
    def test_timed_event_roundtrip(self):
        ev = Event(
            uid="abc@x",
            calendar_uid="cal1",
            summary="Team-Meeting",
            location="Raum 4",
            description="Wöchentlich",
            start=aware(10, 0),
            end=aware(11, 30),
        )
        ics = ev.to_ics()
        assert "BEGIN:VCALENDAR" in ics and "BEGIN:VEVENT" in ics
        parsed = Event.from_ics(ics, calendar_uid="cal1", href="/cal1/abc.ics", etag='"1"')
        assert len(parsed) == 1
        p = parsed[0]
        assert p.uid == "abc@x"
        assert p.summary == "Team-Meeting"
        assert p.location == "Raum 4"
        assert p.description == "Wöchentlich"
        assert not p.all_day
        assert p.start_local == ev.start_local
        assert p.end_local == ev.end_local
        assert p.href == "/cal1/abc.ics"

    def test_all_day_event_roundtrip(self):
        ev = Event(
            uid="d1@x",
            calendar_uid="cal1",
            summary="Urlaub",
            start=datetime(2025, 3, 10),
            end=datetime(2025, 3, 13),
            all_day=True,
        )
        parsed = Event.from_ics(ev.to_ics(), calendar_uid="cal1")
        p = parsed[0]
        assert p.all_day
        assert p.start_date == date(2025, 3, 10)
        assert p.end_date == date(2025, 3, 13)

    def test_multiple_vevents(self):
        ics = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//test//DE",
                "BEGIN:VEVENT",
                "UID:e1@x",
                "DTSTART:20250116T100000Z",
                "DTEND:20250116T110000Z",
                "SUMMARY:Eins",
                "END:VEVENT",
                "BEGIN:VEVENT",
                "UID:e2@x",
                "DTSTART:20250116T120000Z",
                "DTEND:20250116T130000Z",
                "SUMMARY:Zwei",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        events = Event.from_ics(ics, calendar_uid="cal1")
        assert {e.uid for e in events} == {"e1@x", "e2@x"}

    def test_invalid_ics_returns_empty(self):
        assert Event.from_ics("kein kalender", calendar_uid="c") == []

    def test_missing_dtend_gets_one_hour(self):
        ics = "\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "UID:e3@x",
                "DTSTART:20250116T100000Z",
                "SUMMARY:Ohne Ende",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        p = Event.from_ics(ics)[0]
        assert p.end_local - p.start_local == timedelta(hours=1)


class TestEventQueries:
    def test_occurs_on(self):
        ev = Event(start=aware(10), end=aware(11), all_day=False)
        assert ev.occurs_on(date(2025, 1, 16))
        assert ev.occurs_on(date(2025, 1, 17)) is False

    def test_all_day_occurs_on_range(self):
        ev = Event(
            start=datetime(2025, 3, 10),
            end=datetime(2025, 3, 13),
            all_day=True,
        )
        assert ev.occurs_on(date(2025, 3, 10))
        assert ev.occurs_on(date(2025, 3, 12))
        assert ev.occurs_on(date(2025, 3, 13)) is False  # DTEND exklusiv

    def test_overlaps(self):
        a = Event(start=aware(10), end=aware(12))
        assert a.overlaps(aware(11), aware(13))
        assert not a.overlaps(aware(12), aware(13))


class TestCalendarInfo:
    def test_row_roundtrip(self):
        cal = CalendarInfo(uid="u1", name="Privat", color="#34C759", href="https://x", readonly=True)
        row = cal.to_row()
        assert json.dumps(row)  # serialisierbar
        cal2 = CalendarInfo.from_row(row)
        assert cal2 == cal
