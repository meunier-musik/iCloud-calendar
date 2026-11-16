from datetime import date, datetime, timedelta

import pytest

from icloud_calendar.model import LOCAL_TZ, CalendarInfo, Event
from icloud_calendar.storage import Storage


@pytest.fixture()
def storage(tmp_path):
    s = Storage(tmp_path / "test.db")
    yield s
    s.close()


def aware(h, m=0, day=16):
    return datetime(2025, 1, day, h, m, tzinfo=LOCAL_TZ)


def make_event(uid, start, end, cal="cal1", **kw):
    return Event(uid=uid, calendar_uid=cal, summary=f"Termin {uid}", start=start, end=end, **kw)


class TestCalendars:
    def test_upsert_and_get(self, storage):
        cal = CalendarInfo(uid="cal1", name="Privat", color="#FF3B30", href="https://x/cal1/")
        storage.upsert_calendar(cal)
        got = storage.get_calendar("cal1")
        assert got.name == "Privat"
        assert got.color == "#FF3B30"

    def test_upsert_updates(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="B", color="#34C759"))
        assert storage.get_calendar("cal1").name == "B"
        assert len(storage.get_calendars()) == 1

    def test_delete_cascades_events(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        storage.upsert_event(make_event("e1", aware(9), aware(10)))
        storage.delete_calendar("cal1")
        assert storage.get_calendar("cal1") is None
        assert storage.get_event("e1") is None


class TestEvents:
    def test_upsert_and_get(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        ev = make_event("e1", aware(9), aware(10), location="Büro")
        storage.upsert_event(ev)
        got = storage.get_event("e1", "cal1")
        assert got.summary == "Termin e1"
        assert got.location == "Büro"
        assert got.start_local == ev.start_local

    def test_get_events_between(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        storage.upsert_event(make_event("early", aware(8), aware(9)))
        storage.upsert_event(make_event("in", aware(10), aware(11)))
        storage.upsert_event(make_event("late", aware(15), aware(16)))
        events = storage.get_events_between(aware(9, 30), aware(11, 30))
        assert [e.uid for e in events] == ["in"]

    def test_get_events_on_day(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        storage.upsert_event(make_event("d1", aware(9), aware(10)))
        storage.upsert_event(make_event("d2", aware(9, day=17), aware(10, day=17)))
        events = storage.get_events_on_day(date(2025, 1, 16))
        assert [e.uid for e in events] == ["d1"]

    def test_replace_calendar_events(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        storage.upsert_event(make_event("old", aware(9), aware(10)))
        storage.replace_calendar_events(
            "cal1",
            [make_event("n1", aware(11), aware(12)), make_event("n2", aware(13), aware(14))],
        )
        events = storage.get_events_on_day(date(2025, 1, 16))
        assert {e.uid for e in events} == {"n1", "n2"}

    def test_delete_event(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="cal1", name="A"))
        storage.upsert_event(make_event("e1", aware(9), aware(10)))
        storage.delete_event("e1", "cal1")
        assert storage.get_event("e1") is None

    def test_persistence_across_connections(self, tmp_path):
        from icloud_calendar.storage import Storage as S

        s1 = S(tmp_path / "p.db")
        s1.upsert_calendar(CalendarInfo(uid="cal1", name="X"))
        s1.upsert_event(make_event("e1", aware(9), aware(10)))
        s1.close()
        s2 = S(tmp_path / "p.db")
        assert s2.get_event("e1").summary == "Termin e1"
        s2.close()
