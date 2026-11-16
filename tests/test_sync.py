from datetime import date, datetime, timedelta
from threading import Event as ThreadEvent
from unittest.mock import MagicMock, patch

import pytest

from icloud_calendar.model import LOCAL_TZ, CalendarInfo, Event
from icloud_calendar.storage import Storage
from icloud_calendar.sync.caldav_client import ICloudClient, SyncError, _normalize_color
from icloud_calendar.sync.manager import SyncManager


def aware(h, m=0, day=16):
    return datetime(2025, 1, day, h, m, tzinfo=LOCAL_TZ)


@pytest.fixture()
def storage(tmp_path):
    s = Storage(tmp_path / "s.db")
    yield s
    s.close()


def ics_event(uid, summary, dtstart, dtend):
    return "\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//t//DE",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"SUMMARY:{summary}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
    )


class TestNormalizeColor:
    def test_plain_hex(self):
        assert _normalize_color("#FF3B30") == "#FF3B30"

    def test_with_alpha(self):
        assert _normalize_color("#FF3B3080") == "#FF3B30"

    def test_quoted(self):
        assert _normalize_color('"#34C759"') == "#34C759"


class TestSyncManager:
    def _make_manager(self, storage, calendars, events_by_cal):
        client = MagicMock(spec=ICloudClient)
        client.list_calendars.return_value = calendars
        client.fetch_events.side_effect = lambda cal, start=None, end=None: events_by_cal.get(cal.uid, [])
        return SyncManager(storage, client), client

    def test_sync_downloads_calendars_and_events(self, storage):
        cal = CalendarInfo(uid="c1", name="Privat", color="#FF3B30", href="https://x/c1/")
        events = Event.from_ics(
            ics_event("e1", "Meeting", "20250116T090000Z", "20250116T100000Z"), calendar_uid="c1"
        )
        mgr, client = self._make_manager(storage, [cal], {"c1": events})
        mgr.sync()
        client.connect.assert_called_once()
        assert [c.uid for c in storage.get_calendars()] == ["c1"]
        got = storage.get_event("e1", "c1")
        assert got.summary == "Meeting"

    def test_sync_removes_deleted_calendars(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="gone", name="Alt"))
        cal = CalendarInfo(uid="c1", name="Privat")
        mgr, _ = self._make_manager(storage, [cal], {"c1": []})
        mgr.sync()
        assert {c.uid for c in storage.get_calendars()} == {"c1"}

    def test_sync_keeps_local_color(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="c1", name="Alt", color="#34C759"))
        cal = CalendarInfo(uid="c1", name="Privat", color="#FF3B30")
        mgr, _ = self._make_manager(storage, [cal], {"c1": []})
        mgr.sync()
        assert storage.get_calendar("c1").color == "#34C759"

    def test_sync_error_propagates(self, storage):
        client = MagicMock(spec=ICloudClient)
        client.connect.side_effect = SyncError("Verbindung fehlgeschlagen")
        mgr = SyncManager(storage, client)
        with pytest.raises(SyncError):
            mgr.sync()

    def test_sync_async_reports_error(self, storage):
        client = MagicMock(spec=ICloudClient)
        client.connect.side_effect = SyncError("boom")
        mgr = SyncManager(storage, client)
        result = {}
        done = ThreadEvent()

        def on_done(err):
            result["err"] = err
            done.set()

        mgr.sync_async(on_done)
        assert done.wait(5)
        assert "boom" in result["err"]

    def test_create_event_local_only_without_href(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="local", name="Lokal", href=""))
        mgr = SyncManager(storage, MagicMock(spec=ICloudClient))
        ev = Event(uid="x1", calendar_uid="local", summary="Lokal-Termin",
                   start=aware(9), end=aware(10))
        mgr.create_event(ev)
        assert storage.get_event("x1", "local").summary == "Lokal-Termin"

    def test_create_event_uploads(self, storage):
        cal = CalendarInfo(uid="c1", name="Privat", href="https://x/c1/")
        storage.upsert_calendar(cal)
        client = MagicMock(spec=ICloudClient)
        client.put_event.return_value = "https://x/c1/e1.ics"
        mgr = SyncManager(storage, client)
        ev = Event(uid="e1", calendar_uid="c1", summary="Neu", start=aware(9), end=aware(10))
        mgr.create_event(ev)
        client.put_event.assert_called_once()
        assert ev.href == "https://x/c1/e1.ics"
        assert storage.get_event("e1", "c1") is not None

    def test_create_event_readonly_calendar_fails(self, storage):
        storage.upsert_calendar(CalendarInfo(uid="r1", name="Feiertage", readonly=True))
        mgr = SyncManager(storage, MagicMock(spec=ICloudClient))
        ev = Event(uid="e1", calendar_uid="r1", start=aware(9), end=aware(10))
        with pytest.raises(SyncError):
            mgr.create_event(ev)

    def test_delete_event(self, storage):
        cal = CalendarInfo(uid="c1", name="P", href="https://x/c1/")
        storage.upsert_calendar(cal)
        ev = Event(uid="e1", calendar_uid="c1", href="https://x/c1/e1.ics",
                   start=aware(9), end=aware(10))
        storage.upsert_event(ev)
        client = MagicMock(spec=ICloudClient)
        mgr = SyncManager(storage, client)
        mgr.delete_event(ev)
        client.delete_event.assert_called_once()
        assert storage.get_event("e1", "c1") is None


class TestICloudClient:
    def test_init_defaults(self):
        c = ICloudClient("user", "pass")
        assert c.url == "https://caldav.icloud.com/"
        assert c._client is None

    def test_connect_auth_error_becomes_sync_error(self):
        from caldav.lib.error import AuthorizationError

        c = ICloudClient("u", "p")
        with patch("caldav.DAVClient") as mock:
            mock.return_value.principal.side_effect = AuthorizationError("401")
            with pytest.raises(SyncError) as exc:
                c.connect()
            assert "App-spezifisches Passwort" in str(exc.value)
