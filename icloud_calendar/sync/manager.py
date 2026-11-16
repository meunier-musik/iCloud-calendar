"""Sync-Manager: hält iCloud und lokalen Cache synchron."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Optional

from ..model import Event
from ..storage import Storage
from .caldav_client import ICloudClient, SyncError

log = logging.getLogger(__name__)

ProgressCb = Callable[[str], None]


class SyncManager:
    """Führt die Synchronisation in einem Hintergrundthread aus."""

    def __init__(self, storage: Storage, client: ICloudClient):
        self.storage = storage
        self.client = client
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._last_sync: Optional[datetime] = None
        self.last_error: Optional[str] = None

    @property
    def syncing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def sync_async(self, on_done: Callable[[Optional[str]], None], on_progress: Optional[ProgressCb] = None) -> None:
        """Startet einen Sync im Hintergrund. on_done(error) wird im Thread aufgerufen."""

        def run():
            error = None
            try:
                self.sync(on_progress)
            except SyncError as e:
                error = str(e)
            except Exception as e:
                log.exception("Unerwarteter Sync-Fehler")
                error = f"Unerwarteter Fehler: {e}"
            self.last_error = error
            on_done(error)

        with self._lock:
            if self.syncing:
                return
            self._thread = threading.Thread(target=run, daemon=True, name="icloud-sync")
            self._thread.start()

    def sync(self, on_progress: Optional[ProgressCb] = None) -> None:
        """Vollsynchronisation: Kalender + Termine herunterladen."""
        progress = on_progress or (lambda msg: None)

        progress("Verbinde mit iCloud …")
        self.client.connect()
        try:
            progress("Lade Kalenderliste …")
            remote_cals = self.client.list_calendars()
            local_cals = {c.uid: c for c in self.storage.get_calendars()}

            remote_uids = set()
            for cal in remote_cals:
                remote_uids.add(cal.uid)
                # Farbe/Name lokal behalten, wenn der Nutzer sie geändert hat
                old = local_cals.get(cal.uid)
                if old:
                    cal.color = old.color or cal.color
                self.storage.upsert_calendar(cal)

                progress(f"Lade Termine aus „{cal.name}“ …")
                events = self.client.fetch_events(cal)
                self.storage.replace_calendar_events(cal.uid, events)

            for uid in set(local_cals) - remote_uids:
                self.storage.delete_calendar(uid)

            self._last_sync = datetime.now()
            progress("Synchronisation abgeschlossen.")
        finally:
            self.client.disconnect()

    # ---------- Schreiboperationen ----------

    def create_event(self, event: Event) -> Event:
        """Legt den Termin lokal und (wenn möglich) in iCloud an."""
        cal = self.storage.get_calendar(event.calendar_uid)
        if cal is None:
            raise SyncError("Unbekannter Kalender.")
        if cal.readonly:
            raise SyncError(f"Kalender „{cal.name}“ ist schreibgeschützt.")
        if self.client and cal.href:
            try:
                event.href = self.client.put_event(cal, event)
            except SyncError as e:
                log.warning("Upload fehlgeschlagen, speichere nur lokal: %s", e)
        self.storage.upsert_event(event)
        return event

    def update_event(self, event: Event) -> Event:
        old = self.storage.get_event(event.uid, event.calendar_uid)
        cal = self.storage.get_calendar(event.calendar_uid)
        if cal is None:
            raise SyncError("Unbekannter Kalender.")
        if not cal.readonly and self.client and (cal.href or (old and old.href)):
            try:
                event.href = self.client.put_event(cal, event)
            except SyncError as e:
                log.warning("Upload fehlgeschlagen, speichere nur lokal: %s", e)
        self.storage.upsert_event(event)
        return event

    def delete_event(self, event: Event) -> None:
        cal = self.storage.get_calendar(event.calendar_uid)
        if cal and not cal.readonly and self.client and event.href:
            try:
                self.client.delete_event(cal, event)
            except SyncError as e:
                log.warning("Löschen in iCloud fehlgeschlagen: %s", e)
        self.storage.delete_event(event.uid, event.calendar_uid)
