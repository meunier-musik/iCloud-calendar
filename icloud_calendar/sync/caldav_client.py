"""CalDAV-Client für iCloud (caldav.icloud.com).

iCloud verlangt ein App-spezifisches Passwort:
appleid.apple.com → Anmelden und Sicherheit → App-spezifische Passwörter.
"""

from __future__ import annotations

import logging
from typing import Optional

import caldav
from caldav.lib.error import AuthorizationError, NotFoundError

from ..model import APPLE_CALENDAR_COLORS, CalendarInfo, Event

log = logging.getLogger(__name__)

ICLOUD_URL = "https://caldav.icloud.com/"


class SyncError(Exception):
    pass


class ICloudClient:
    """Dünner Wrapper um die caldav-Bibliothek für iCloud."""

    def __init__(self, username: str, password: str, url: str = ICLOUD_URL):
        self.username = username
        self.password = password
        self.url = url
        self._client: Optional[caldav.DAVClient] = None
        self._principal = None

    # ---------- Verbindung ----------

    def connect(self) -> None:
        try:
            self._client = caldav.DAVClient(
                url=self.url,
                username=self.username,
                password=self.password,
            )
            self._principal = self._client.principal()
        except AuthorizationError as e:
            raise SyncError(
                "Anmeldung fehlgeschlagen. Bitte Apple-ID und App-spezifisches "
                "Passwort prüfen (nicht das normale Apple-Passwort!)."
            ) from e
        except Exception as e:  # Netzwerk, DNS, SSL …
            raise SyncError(f"Verbindung zu iCloud fehlgeschlagen: {e}") from e
        if self._principal is None:
            raise SyncError("iCloud-Principal konnte nicht ermittelt werden.")

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._principal = None

    def test_connection(self) -> None:
        self.connect()
        self.disconnect()

    # ---------- Kalender ----------

    def list_calendars(self) -> list[CalendarInfo]:
        if self._principal is None:
            self.connect()
        result: list[CalendarInfo] = []
        for i, cal in enumerate(self._principal.calendars()):
            name = cal.name or "Kalender"
            color = "#007AFF"
            try:
                props = cal.get_properties([caldav.dav.CalendarColor()])
                if props is not None:
                    raw = props.get("{http://apple.com/ns/ical/}calendarcolor")
                    if raw:
                        color = _normalize_color(str(raw))
            except Exception:
                pass
            readonly = _is_readonly(cal)
            result.append(
                CalendarInfo(
                    uid=str(cal.id),
                    name=name,
                    color=color if color.startswith("#") else APPLE_CALENDAR_COLORS[i % len(APPLE_CALENDAR_COLORS)],
                    href=str(cal.url),
                    readonly=readonly,
                )
            )
        return result

    def _calendar_obj(self, cal: CalendarInfo):
        if self._client is None:
            self.connect()
        return caldav.Calendar(self._client, url=cal.href)

    # ---------- Termine ----------

    def fetch_events(self, cal: CalendarInfo, start=None, end=None) -> list[Event]:
        """Lädt alle Termine eines Kalenders (optional im Zeitraum)."""
        cal_obj = self._calendar_obj(cal)
        try:
            if start is not None and end is not None:
                results = cal_obj.search(start=start, end=end, expand=False)
            else:
                results = cal_obj.events()
        except NotFoundError:
            return []
        except Exception as e:
            raise SyncError(f"Termine konnten nicht geladen werden ({cal.name}): {e}") from e
        events = []
        for r in results:
            try:
                ics = r.data
                href = str(r.url)
                etag = ""
                try:
                    etag = r.canonical_etag or ""
                except Exception:
                    pass
                events.extend(Event.from_ics(ics, calendar_uid=cal.uid, href=href, etag=etag))
            except Exception:
                log.exception("Termin konnte nicht geparst werden: %s", r.url)
        return events

    def put_event(self, cal: CalendarInfo, event: Event) -> str:
        """Erzeugt oder aktualisiert einen Termin. Gibt die href zurück."""
        cal_obj = self._calendar_obj(cal)
        try:
            obj = cal_obj.save_event(event.to_ics(), uid=event.uid)
            href = str(obj.url)
        except Exception as e:
            raise SyncError(f"Termin konnte nicht zu iCloud hochgeladen werden: {e}") from e
        return href

    def delete_event(self, cal: CalendarInfo, event: Event) -> None:
        cal_obj = self._calendar_obj(cal)
        try:
            if event.href:
                obj = caldav.CalendarObjectResource(self._client, url=event.href, parent=cal_obj)
                obj.delete()
            else:
                evs = cal_obj.search(uid=event.uid)
                for ev in evs:
                    ev.delete()
        except NotFoundError:
            return
        except Exception as e:
            raise SyncError(f"Termin konnte nicht in iCloud gelöscht werden: {e}") from e


def _normalize_color(raw: str) -> str:
    """iCloud liefert Farben teils als '#RRGGBBAA' oder mit Anführungszeichen."""
    raw = raw.strip().strip('"').strip("'")
    if raw.startswith("#"):
        body = raw[1:].split(",")[0]
        if len(body) >= 6:
            return "#" + body[:6]
    return raw


def _is_readonly(cal) -> bool:
    """Prüft, ob der Kalender beschreibbar ist (z. B. Geburtstage, Feiertage)."""
    try:
        props = cal.get_properties([caldav.dav.CurrentUserPrivilegeSet()])
        priv = props.get("{DAV:}current-user-privilege-set")
        if priv is None:
            return False
        xml = priv.toxml() if hasattr(priv, "toxml") else str(priv)
        return "all" not in xml and "write" not in xml
    except Exception:
        return False
