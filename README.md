# Kalender für Ubuntu mit iCloud-Sync

Eine native GTK4/libadwaita-Kalender-App im Look & Feel von **Apple Calendar**,
die direkt mit deinem **iCloud-Kalender** synchronisiert (CalDAV).

## Funktionen

- **Ansichten:** Tag, Woche, Monat, Jahr – wie im Apple Calendar
  - Monatsansicht mit farbigen Termin-Pills und roter „Heute“-Markierung
  - Wochen-/Tagesansicht als echtes Zeitraster mit Ganztages-Band und roter Jetzt-Linie
  - Jahresansicht mit 12 Mini-Monaten und Termin-Punkten
- **iCloud-Sync** über CalDAV (`caldav.icloud.com`)
  - Kalenderliste, Farben und Termine werden automatisch geladen
  - Termine anlegen, bearbeiten und löschen – werden sofort zu iCloud hochgeladen
  - Automatische Synchronisierung alle 15 Minuten + manuell per Button
- **Offline-fähig:** lokaler SQLite-Cache, Termine auch ohne Netz sichtbar und anlegbar
- **Lokaler Kalender** für Termine ohne iCloud
- **Apple-Design:** rote Akzentfarbe (#FF3B30), helle Flächen, SF-ähnliche Typografie
- Deutsche Oberfläche, Wochenstart Montag
- Tastenkürzel: `Strg+T` Heute · `Strg+N` Neuer Termin · `Strg+R` Synchronisieren ·
  `Strg+1–4` Ansicht wechseln · `Strg+←/→` Blättern

## Voraussetzungen

- Ubuntu 22.10 / 23.04 / 24.04 LTS / 25.04 (GTK 4.8+, libadwaita 1.2+)
- Python 3.10+

## Installation

```bash
cd icloud-calendar
./install.sh
```

Das Skript installiert die Systempakete (GTK4, libadwaita), legt eine virtuelle
Python-Umgebung an und registriert die App im Anwendungsmenü.

Starten danach entweder über das Menü (**Kalender**) oder per:

```bash
.venv/bin/icloud-calendar
```

### Manuelle Installation

```bash
sudo apt-get install python3-venv python3-gi python3-gi-cairo \
    gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps -e .
bin/icloud-calendar
```

## iCloud-Konto verbinden

iCloud akzeptiert **kein normales Apple-Passwort** – es wird ein
**App-spezifisches Passwort** benötigt:

1. Auf [appleid.apple.com](https://appleid.apple.com) anmelden
2. **Anmelden und Sicherheit → App-spezifische Passwörter**
3. Ein neues Passwort erzeugen (z. B. „Ubuntu Kalender“)
4. In der App beim ersten Start **Apple-ID + App-Passwort** eingeben

Die Zugangsdaten werden lokal unter `~/.config/icloud-calendar/config.json`
gespeichert (Dateirechte 0600, nur für den eigenen Benutzer lesbar).

Synchronisiert werden alle iCloud-Kalender, einschließlich der geteilten.
Schreibgeschützte Kalender (z. B. „Feiertage“, „Geburtstage“) werden erkannt
und nur angezeigt.

## Datenschutz

- Die App verbindet sich **ausschließlich** mit `caldav.icloud.com` (Apple).
- Termine werden lokal in `~/.cache/icloud-calendar/calendar.db` zwischengespeichert.
- Keine Telemetrie, keine weiteren Server.

## Entwicklung

```bash
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests/
```

Projektstruktur:

```
icloud_calendar/
├── main.py               # Adw.Application, Einstiegspunkt
├── window.py             # Hauptfenster, Kopfzeile, Seitenleiste, Navigation
├── model.py              # Event/CalendarInfo + iCal-(De-)Serialisierung
├── storage.py            # SQLite-Offline-Cache
├── config.py             # Konfiguration (~/.config/icloud-calendar)
├── sync/
│   ├── caldav_client.py  # iCloud-CalDAV-Client (caldav.icloud.com)
│   └── manager.py        # Sync-Steuerung im Hintergrundthread
├── views/                # Monat, Woche/Tag, Jahr
└── widgets/              # Termin-Editor, Konto-Dialog
```

## Fehlerbehebung

| Problem | Lösung |
| --- | --- |
| „Anmeldung fehlgeschlagen“ | Es muss ein **App-spezifisches Passwort** sein, nicht das Apple-Passwort |
| Keine Kalender sichtbar | Sync-Button drücken; prüfen, ob Kalender in iCloud unter „Kalender“ aktiviert sind |
| App startet nicht | `sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi python3-gi-cairo` |
| Doppelte Termine | Termine gehören zu iCloud – nicht zusätzlich in GNOME Calendar für dasselbe Konto anlegen |

## Lizenz

MIT
