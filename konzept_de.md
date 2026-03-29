# Konzept: HA Advanced Timer & Calendar

## 1. Überblick & Ziele

Eine Custom Component für Home Assistant, die folgende Kernbereiche abdeckt:

- **Timer / Scheduler**: Steuerung von Entitäten (Switches, Lights, etc.) nach Zeitplan
- **Reminder / Kalender**: Erinnerungen, Termine, Jahrestage, ToDos
- **Telegram-Integration**: Benachrichtigungen und bidirektionale Bot-Steuerung (interaktiv wenn HA Telegram Bot vorhanden)
- **Bidirektionale Kalenderanbindung**: Vollständige Synchronisation mit Microsoft 365/Outlook, Google Calendar und Apple iCloud Calendar – für mehrere Personen/Accounts gleichzeitig
- **Persistenz**: Alle Daten überleben HA-Neustarts
- **Laienfreundlichkeit**: Vollständige Konfiguration über die HA-UI (Config Flow + Options Flow)
- **Mehrinstanzen-fähig**: Mehrere unabhängige Instanzen parallel möglich (z.B. „Garten", „Haus")
- **Eigenes Dashboard + Lovelace Cards**: Mitgeliefertes Dashboard sowie eigenständige Cards für benutzerdefinierte Dashboards
- **HACS-konform**: Von Anfang an HACS-kompatibel, einfache Installation und Updates

**Mindest-Anforderung**: Home Assistant 2026.0+

---

## 2. Architektur

### 2.1 Komponentenstruktur

```
custom_components/advanced_timer_calendar/
├── __init__.py              # Setup, Coordinator-Start, Multi-Instance-Support
├── manifest.json            # Metadaten, Abhängigkeiten (HACS-konform)
├── config_flow.py           # Einrichtungsassistent (UI), Multi-Instance
├── options_flow.py          # Nachträgliche Einstellungen
├── const.py                 # Konstanten, Enums, DOMAIN
├── coordinator.py           # Zentraler DataUpdateCoordinator
├── storage.py               # Persistenz via HA Storage API (mit Migrations-Engine)
├── scheduler.py             # Timer-Logik & Scheduling-Engine
├── calendar.py              # Calendar-Plattform (CalendarEntity)
├── sensor.py                # Sensor-Plattform (Status, nächster Trigger)
├── switch.py                # Switch-Plattform (Timer ein/aus)
├── services.yaml            # HA-Service-Definitionen
├── services.py              # Service-Handler
├── telegram_bot.py          # Telegram-Benachrichtigungs- & Steuerungsmodul
│                            # (interaktiv/bidirektional via HA telegram_bot)
├── external_calendars/
│   ├── __init__.py          # Paket-Init, Provider-Registry
│   ├── base.py              # Abstrakte Basisklasse CalendarProvider
│   ├── microsoft.py         # Microsoft 365 / Outlook (Graph API)
│   ├── google.py            # Google Calendar API
│   ├── apple.py             # Apple iCloud Calendar (CalDAV)
│   ├── sync_engine.py       # Bidirektionale Sync-Logik & Konfliktlösung
│   ├── trigger_processor.py # Terminbasierte HA-Trigger-Auswertung
│   └── oauth_handler.py     # OAuth2-Flows (PKCE, Device Code)
├── translations/
│   ├── de.json
│   └── en.json
├── strings.json
└── www/                     # Lovelace Custom Cards (HACS frontend)
    ├── atc-timer-card.js    # Timer-Übersichtskarte
    ├── atc-reminder-card.js # Kalender/Reminder-Karte
    └── atc-status-card.js   # System-Statuskarte

hacs.json                    # HACS-Manifest (Repo-Root)
dashboard/
└── atc_dashboard.yaml       # Mitgeliefertes Standard-Dashboard
```

### 2.2 Datenhaltung

**HA Storage API** (`.storage/advanced_timer_calendar`) – JSON-Datei, die bei jedem Schreiben gespeichert wird. Kein Verlust bei Neustart.

Datenstruktur (vereinfacht):

```json
{
  "version": 1,
  "schema_version": 1,
  "timers": [ { "...Timer-Objekt..." } ],
  "reminders": [ { "...Reminder-Objekt..." } ],
  "calendar_accounts": [
    {
      "id": "uuid",
      "provider": "microsoft|google|apple",
      "display_name": "Max Mustermann – Arbeit",
      "credentials": { "...OAuth-Token (verschlüsselt)..." },
      "calendars": [
        {
          "remote_id": "...",
          "name": "Kalender-Name",
          "sync_enabled": true,
          "sync_direction": "bidirectional|inbound|outbound",
          "color": "#0078d4"
        }
      ]
    }
  ],
  "calendar_triggers": [ { "...Trigger-Objekt..." } ],
  "settings": { "...globale Einstellungen..." }
}
```

### 2.3 Storage-Schema-Migration

Das Storage-File enthält das Feld `schema_version`. Bei jedem Start prüft die Integration die gespeicherte Version gegen die aktuelle Versions-Konstante:

```python
STORAGE_VERSION = 1  # In const.py – bei brechenden Änderungen erhöhen
```

**Migrations-Engine** (`storage.py`):
- Beim Laden: `schema_version` aus Datei lesen
- Falls `schema_version < STORAGE_VERSION`: Migrations-Funktionen sequenziell anwenden
- Jede Migration ist eine eigene Funktion (`migrate_v1_to_v2`, `migrate_v2_to_v3`, ...)
- Nach erfolgreicher Migration: Daten mit neuer `schema_version` zurückschreiben
- Bei Fehler: Backup der alten Datei unter `.storage/advanced_timer_calendar.bak` anlegen, Fehler loggen

**Beispiel-Migration (v1 → v2)**:
```python
def migrate_v1_to_v2(data: dict) -> dict:
    # Beispiel: Neues Pflichtfeld 'tags' zu allen Timern hinzufügen
    for timer in data.get("timers", []):
        timer.setdefault("tags", [])
    data["schema_version"] = 2
    return data
```

---

## 3. Timer / Scheduler

### 3.1 Timer-Objekt (Datenmodell)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `id` | UUID | Eindeutige ID |
| `name` | string | Anzeigename |
| `enabled` | bool | Aktiv/Inaktiv |
| `schedule_type` | enum | `once`, `daily`, `weekdays`, `interval`, `yearly` |
| `time` | time | Uhrzeit des Triggers (None = ganztägig) |
| `all_day` | bool | Ganztagstermin |
| `weekdays` | list[int] | 0=Mo…6=So |
| `interval_value` | int | z.B. 2 |
| `interval_unit` | enum | `days`, `weeks`, `months` |
| `start_date` | date | Startdatum |
| `end_date` | date\|None | Enddatum (None = unbegrenzt) |
| `actions` | list | Aktionen bei Trigger |
| `conditions` | list | Bedingungen (Entitäten, Zeitfenster) |
| `duration` | int\|None | Dauer in Sekunden (z.B. Bewässerung 10 min) |
| `notification` | dict\|None | Benachrichtigungsconfig |

### 3.2 Schedule-Typen

| Typ | Beschreibung | Beispiel |
|-----|-------------|---------|
| `once` | Einmalig | Morgen 07:00 |
| `daily` | Täglich | Jeden Tag 06:30 |
| `weekdays` | Wochentage | Mo, Mi, Fr 08:00 |
| `interval` | Alle X Tage/Wochen/Monate | Alle 3 Tage |
| `yearly` | Jährlich | Jedes Jahr am 1. Juni |
| `cron` | Fortgeschrittene Nutzer (optional) | Cron-Ausdruck |

### 3.3 Aktionen (Action-Objekte)

Jede Aktion besteht aus:

- **Ziel**: Entity ID(s) (z.B. `switch.garden_valve_1`) – mehrere möglich
- **Aktion**: `turn_on`, `turn_off`, `toggle`, `set_value`, HA-Service-Aufruf
- **Verzögerung**: optionale Verzögerung nach Trigger (z.B. Bewässerung Sektor 2 startet 5 min nach Sektor 1)
- **Dauer**: automatisches Ausschalten nach X Sekunden/Minuten

**Bewässerungsbeispiel:**

```
Trigger: täglich 06:00
Aktion 1: switch.valve_zone_1 → ON, Dauer 10 min
Aktion 2: switch.valve_zone_2 → ON, Verzögerung 10 min, Dauer 8 min
Aktion 3: switch.valve_zone_3 → ON, Verzögerung 18 min, Dauer 12 min
```

### 3.4 Bedingungen

Bedingungen blockieren den Timer-Trigger wenn nicht erfüllt:

- **Entitätszustand**: z.B. `sensor.rain_sensor == 'raining'` → Timer überspringen
- **Zeitfenster**: Nur ausführen wenn zwischen 06:00–20:00
- **Numerischer Schwellwert**: z.B. `sensor.soil_moisture < 30`
- **Template**: Beliebiges HA-Template

### 3.5 Scheduling-Engine

- `asyncio`-basiert, läuft im HA Event Loop
- Nächster Ausführungszeitpunkt wird bei Start berechnet und in einem `async_track_point_in_time`-Callback registriert
- Nach jedem Trigger: nächsten Zeitpunkt berechnen und neu registrieren
- Bei HA-Neustart: alle Timer aus Storage laden, Callbacks neu registrieren

---

## 4. Reminder / Kalender

### 4.1 Reminder-Objekt

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `id` | UUID | Eindeutige ID |
| `title` | string | Titel |
| `description` | string | Beschreibung |
| `type` | enum | `reminder`, `todo`, `anniversary`, `appointment` |
| `date` | date | Datum |
| `time` | time\|None | Uhrzeit (None = ganztägig) |
| `recurrence` | dict\|None | Wiederholungsregel |
| `reminder_before` | int | Vorlaufzeit Benachrichtigung (Minuten) |
| `tags` | list[str] | Kategorien / Tags |
| `completed` | bool | Für ToDos: erledigt |
| `notification` | dict\|None | Benachrichtigungsconfig |

### 4.2 Kalender-Plattform

Implementierung als `CalendarEntity` – damit erscheint die Integration im HA-Kalender und ist vollständig kompatibel mit dem HA-Calendar-Dashboard.

Separate Kalender (als einzelne Entities) pro Typ:

- `calendar.atc_appointments` – Termine
- `calendar.atc_anniversaries` – Jahrestage
- `calendar.atc_todos` – ToDos
- `calendar.atc_timer_schedule` – Übersicht aller Timer-Trigger

### 4.3 ToDo-Integration

Optionale Anbindung an die HA-eigene `todo`-Plattform (ab HA 2023.11) für native ToDo-Listen im Dashboard.

---

## 5. Telegram-Integration

### 5.1 Betriebsmodi

**Modus A – Eigenständig** (einfach): Direkte Eingabe von Bot-Token + Chat-ID im Config Flow → die Integration sendet selbst Nachrichten über die Telegram Bot API. Nur ausgehende Benachrichtigungen, keine eingehenden Befehle.

**Modus B – HA Telegram Bot** (fortgeschritten, empfohlen): Nutzung der bestehenden `telegram_bot`-Integration in HA. Wenn diese vorhanden ist, wird **bidirektionale und interaktive** Kommunikation aktiviert:
- Ausgehend: Nachrichten und Inline-Keyboards über `notify.<telegram_service>`
- Eingehend: Befehle und Callback-Antworten über HA-Events (`telegram_command`, `telegram_callback`)
- Interaktive Inline-Keyboards für Bestätigungen, Auswahlen und Statusabfragen

### 5.2 Benachrichtigungen

Ausgelöst bei:

- Timer-Trigger (Beginn & Ende)
- Bedingung verhindert Ausführung ("Bewässerung übersprungen – Regen erkannt")
- Reminder/Termin kurz vor Fälligkeit
- ToDo fällig
- Fehler / Timer deaktiviert

Nachrichtenformat konfigurierbar (Template-basiert), z.B.:

```
🌿 Bewässerung Zone 1 gestartet
Dauer: 10 Minuten | Nächste Ausführung: Morgen 06:00
```

### 5.3 Bot-Steuerung (Modus B – HA Telegram Bot)

Über Telegram-Befehle Timer steuern (nur wenn `telegram_bot`-Integration vorhanden):

| Befehl | Funktion |
|--------|---------|
| `/timer list` | Alle Timer anzeigen |
| `/timer pause Garten` | Timer pausieren |
| `/timer resume Garten` | Timer fortsetzen |
| `/timer next Garten` | Nächste Ausführung anzeigen |
| `/reminder list` | Anstehende Reminder |
| `/reminder add ...` | Schnell-Reminder erstellen |
| `/status` | Systemüberblick |

**Inline-Keyboards (interaktiv, Modus B)**:

Beim Eingang eines Timer-Triggers oder einer Erinnerung werden Inline-Keyboard-Buttons mitgesendet:

```
🌿 Bewässerung Zone 1 startet in 5 Minuten
[✅ Bestätigen] [⏭ Überspringen] [⏸ Pausieren (1h)]
```

```
🔔 Erinnerung: Arzttermin in 30 Minuten
[✅ OK] [⏰ +15 Min erinnern] [❌ Abbrechen]
```

Callback-Antworten werden über HA-Events (`telegram_callback`) verarbeitet und lösen die entsprechenden ATC-Services aus.

Sicherheit: Whitelist von Chat-IDs, die Befehle senden dürfen.

---

## 6. HA-Entitäten der Integration

| Entity | Typ | Beschreibung |
|--------|-----|-------------|
| `switch.atc_<name>` | Switch | Timer aktivieren/deaktivieren |
| `sensor.atc_<name>_next_run` | Sensor | Nächste Ausführung (Timestamp) |
| `sensor.atc_<name>_last_run` | Sensor | Letzte Ausführung |
| `sensor.atc_<name>_status` | Sensor | `idle`, `running`, `paused`, `skipped` |
| `calendar.atc_*` | Calendar | Kalenderansichten |

---

## 7. HA-Services

| Service | Parameter | Beschreibung |
|---------|-----------|-------------|
| `atc.create_timer` | name, schedule, actions | Timer erstellen |
| `atc.update_timer` | timer_id, ... | Timer ändern |
| `atc.delete_timer` | timer_id | Timer löschen |
| `atc.enable_timer` | timer_id | Timer aktivieren |
| `atc.disable_timer` | timer_id | Timer deaktivieren |
| `atc.pause_timer` | timer_id, duration | Temporär pausieren |
| `atc.skip_next` | timer_id | Nächste Ausführung überspringen |
| `atc.run_now` | timer_id | Sofort ausführen |
| `atc.create_reminder` | title, date, ... | Reminder erstellen |
| `atc.complete_todo` | reminder_id | ToDo als erledigt markieren |
| `atc.sync_calendar` | account_id | Manuellen Sync für Account anstoßen |
| `atc.add_calendar_account` | provider, display_name | Neuen Kalender-Account hinzufügen |
| `atc.remove_calendar_account` | account_id | Account entfernen (inkl. Daten) |
| `atc.create_external_event` | account_id, calendar_id, title, start, end, ... | Termin in externem Kalender erstellen |
| `atc.delete_external_event` | account_id, event_id | Termin in externem Kalender löschen |
| `atc.create_calendar_trigger` | name, account_id, keyword, lead_time, actions | Kalender-Trigger erstellen |
| `atc.delete_calendar_trigger` | trigger_id | Kalender-Trigger löschen |

---

## 8. Config Flow (Einrichtungsassistent)

### Schritt 1 – Allgemein
- Name der Integration-Instanz

### Schritt 2 – Telegram (optional)
- Modus: "Kein Telegram", "Eigener Bot", "HA Telegram Bot"
- Bei "Eigener Bot": Bot-Token, Chat-ID, Test-Nachricht senden
- Bei "HA Telegram Bot": Auswahl des vorhandenen Notification-Services

### Schritt 3 – Externe Kalender-Accounts (optional, wiederholbar)
- Provider auswählen: Microsoft 365 / Outlook, Google Calendar, Apple iCloud Calendar
- **Microsoft 365**: OAuth2 Device Code Flow (öffnet Browser mit Code) → Benutzer meldet sich bei Microsoft an → Token wird gespeichert
- **Google**: OAuth2 Authorization Code Flow mit PKCE → Redirect auf lokalen HA-Callback → Token wird gespeichert
- **Apple / iCloud**: Eingabe von Apple-ID + App-spezifischem Passwort (kein OAuth, CalDAV-basiert)
- Anzeigename für den Account (z.B. „Max Arbeit", „Familie")
- Nach Authentifizierung: Liste verfügbarer Kalender abrufen und zur Auswahl anzeigen
- Pro Kalender: Sync-Richtung festlegen (`Bidirektional`, `Nur eingehend`, `Nur ausgehend`)
- Mehrere Accounts desselben Providers möglich (z.B. zwei Google-Accounts)
- Sync-Intervall konfigurieren (Empfehlung: alle 5–15 Minuten; Push-Benachrichtigungen wo verfügbar)

### Schritt 4 – Standardeinstellungen
- Standardmäßige Vorlaufzeit für Reminder-Benachrichtigungen
- Zeitzone (Standard: HA-Zeitzone)

### Options Flow
Alle Einstellungen nachträglich änderbar.

---

## 9. Frontend / UI

### 9.1 Native HA-UI
- Config Flow & Options Flow → vollständig über HA-UI bedienbar
- Entitäten erscheinen im HA-Dashboard
- Kalender im HA-Calendar-Dashboard

### 9.2 Eigenes ATC-Dashboard (Phase 1)

Mit der Installation wird automatisch ein vorkonfiguriertes Dashboard (`dashboard/atc_dashboard.yaml`) mitgeliefert und beim ersten Setup in HA registriert. Das Dashboard nutzt ausschließlich die ATC Lovelace Cards (siehe 9.3) und bietet sofort einen vollständigen Überblick:

- **Tab 1 – Timer**: Alle Timer mit Status, nächstem Ausführungszeitpunkt, An/Aus-Schalter
- **Tab 2 – Kalender & Reminder**: Monatsansicht, anstehende Termine, ToDo-Liste
- **Tab 3 – Externe Kalender**: Sync-Status aller Accounts, nächste Events
- **Tab 4 – Einstellungen**: Schnellzugriff auf Options Flow, Benachrichtigungstest

Das Dashboard kann jederzeit deaktiviert oder angepasst werden. Ein Neuerstellen ist per Service möglich.

### 9.3 Lovelace Custom Cards (Phase 1)

Alle Cards werden als eigenständige JavaScript-Module (`www/`) ausgeliefert und sind über HACS automatisch registriert. Sie können sowohl im ATC-Dashboard als auch in beliebigen nutzerdefinierten Dashboards verwendet werden:

#### ATC Timer Card (`atc-timer-card`)
```yaml
type: custom:atc-timer-card
instance: garten        # Optional: ATC-Instanz-Name (bei mehreren Instanzen)
show_disabled: false    # Deaktivierte Timer ausblenden
```
- Übersicht aller Timer der Instanz
- Inline An/Aus-Toggle pro Timer
- Nächste Ausführung als Countdown
- Statusanzeige: `idle`, `running`, `paused`, `skipped`
- Schnellaktionen: Jetzt ausführen, Überspringen, Pausieren

#### ATC Reminder Card (`atc-reminder-card`)
```yaml
type: custom:atc-reminder-card
instance: garten
days_ahead: 7           # Tage im Voraus anzeigen
show_completed: false
```
- Listenansicht anstehender Reminder und Termine
- Farbliche Unterscheidung nach Typ (Termin, Jahrestag, ToDo)
- Inline-Erledigung von ToDos

#### ATC Status Card (`atc-status-card`)
```yaml
type: custom:atc-status-card
instance: garten
```
- Systemüberblick: aktive Timer, anstehende Reminder, Sync-Status
- Telegram-Verbindungsstatus
- Letzte/nächste Aktionen

---

## 10. Technische Entscheidungen

### Getroffene Entscheidungen (alle offenen Fragen geklärt)

| Thema | Entscheidung |
|-------|-------------|
| **Mindest-HA-Version** | HA 2026.0+ (stabile Calendar, ToDo & Event API) |
| **Mehrere Instanzen** | ✅ Ja – via `config_entries`, unbegrenzte Instanzen möglich (z.B. „Garten", „Haus") |
| **Abhängigkeiten** | Ausschließlich HA-interne Mittel oder mit der Integration ausgelieferte Bibliotheken (keine separaten PyPI-Installationen erforderlich) |
| **Storage-Migration** | Versioniertes Schema (`schema_version`), sequenzielle Migrations-Funktionen in `storage.py` (siehe Abschnitt 2.3) |
| **Telegram-Modus** | Modus A (eigenständig, nur Outbound) + Modus B (interaktiv & bidirektional, wenn HA `telegram_bot` vorhanden) |
| **Telegram Bot Commands** | Interaktive Inline-Keyboards für Bestätigungen und Auswahlen in Modus B |
| **Bewässerungslogik** | Generische Bedingungslogik (keine dedizierte Bewässerungs-Engine) – erweiterbar in späteren Phasen |
| **Lovelace Cards** | ✅ Phase 1 – mitgeliefert als eigenständige Custom Cards (`www/`) + eigenes Dashboard |
| **HACS-Kompatibilität** | ✅ Von Anfang an – `hacs.json` im Repo-Root, HACS-konforme Verzeichnisstruktur |
| **UI-Sprachen** | Deutsch und Englisch von Anfang an (`translations/de.json` + `en.json`) |
| **Cron-Ausdrücke** | Optionaler `cron`-Schedule-Typ für fortgeschrittene Nutzer (via enthaltener `croniter`-Bibliothek) |
| **OAuth2-App-Registrierung** | Eigene App-Registrierung durch den Nutzer (Client-ID/Secret im Config Flow eingeben) |
| **Token-Sicherheit** | AES-256-Verschlüsselung via HA `secrets` / `keyring`, kein Klartext in Storage |
| **Konfliktlösung bei Sync** | Konfigurierbar pro Account: `ha_wins`, `remote_wins`, `newest_wins`, `manual` |

### Empfohlene Designentscheidungen

- **Storage statt SQLite**: HA Storage API ist die idiomatische Lösung, kein eigenes Datenbankschema
- **DataUpdateCoordinator**: Zentrales State-Management, alle Plattformen subscriben darauf
- **asyncio nativ**: Keine blocking calls, alles async
- **HACS von Anfang an**: Ermöglicht einfache Distribution und Updates für Laien
- **config_entries**: Multi-Instance-Support über HA-Standard-Mechanismus

---

## 11. Eigene Ideen & Erweiterungen

### 11.1 Bewässerungsassistent „Smart Watering"
Automatische Anpassung der Bewässerungsdauer basierend auf:
- Temperatur-Sensor
- Wettervorhersage (HA Weather Entity)
- Bodenfeuchte-Sensor

→ Algorithmus berechnet optimale Dauer.

### 11.2 „Urlaubs-Modus"
Alle Timer auf "pausiert" setzen für einen definierten Zeitraum (mit einer einzigen Aktion).

### 11.3 Timer-Templates / Vorlagen
Vorgefertigte Timer-Templates für häufige Anwendungsfälle (Bewässerung, Licht-Timer, Thermostat-Zeitplan) – für Laien besonders hilfreich.

### 11.4 Sunrise/Sunset-Trigger
Timer relativ zu Sonnenauf-/-untergang (z.B. "30 min vor Sonnenuntergang Außenlicht einschalten").

### 11.5 Statistiken & History
Sensor mit Anzahl der Ausführungen, übersprungenen Ausführungen, Laufzeiten – als Grundlage für ein HA Energy/Statistics Dashboard.

### 11.6 Benachrichtigungs-Eskalation
Wenn eine Erinnerung nicht "bestätigt" wird (über Telegram-Button), nach X Minuten erneut erinnern.

### 11.7 Import/Export
Timer und Reminder als YAML/JSON exportieren und importieren – nützlich für Backups und Teilen von Konfigurationen.

---

## 12. Phasenplan (Umsetzungsempfehlung)

### Phase 1 – Kern (MVP)
- HACS-Konformität (`hacs.json`, HACS-konforme Struktur)
- Persistenz & Storage (inkl. Migrations-Engine)
- Multi-Instance-Support via `config_entries`
- Scheduler-Engine (`daily`, `weekdays`, `interval`, `yearly`, `once`)
- Aktionen (`turn_on`, `turn_off`, Dauer)
- Bedingungen (Entitätszustand, Template) – generische Bedingungslogik
- HA-Entitäten (Switch, Sensor)
- Config Flow (ohne Telegram, ohne externe Kalender)
- Kalender-Plattform
- Services
- **Lovelace Custom Cards** (`atc-timer-card`, `atc-reminder-card`, `atc-status-card`)
- **ATC-Dashboard** (automatisch installiertes Standard-Dashboard)

### Phase 2 – Telegram & Reminder
- Telegram Modus A (eigenständig, nur Outbound)
- Telegram Modus B (HA-Integration, bidirektional & interaktiv via Inline-Keyboards)
- Reminder/Kalender-Typen (Jahrestage, ToDos)
- HA ToDo-Plattform-Integration
- Sunrise/Sunset-Trigger
- Cron-Schedule-Typ (für fortgeschrittene Nutzer)

### Phase 3 – Externe Kalenderanbindung
- Google Calendar: OAuth2, bidirektionaler Sync, Kalender-Trigger
- Microsoft 365 / Outlook: Graph API, OAuth2 Device Code, bidirektionaler Sync
- Apple iCloud Calendar: CalDAV, bidirektionaler Sync
- Multi-Account-Verwaltung im Config/Options Flow
- Konfigurierbarer Sync-Intervall; Microsoft/Google Webhook-Push-Support
- Kalender-Trigger: Termine als HA-Automations-Trigger
- Outbound-Sync: HA-Timer und Reminder in externe Kalender schreiben

### Phase 4 – Komfort & Erweiterungen
- Smart Watering Algorithmus (Bewässerungsprofil als Erweiterung der generischen Bedingungslogik)
- Timer-Templates
- Import/Export
- Benachrichtigungs-Eskalation
- Statistiken & History
- Weitere Office-Integrationen (Microsoft Teams Präsenz, To Do, etc.)

---

## 13. HACS-Konfiguration

### 13.1 hacs.json (Repo-Root)

```json
{
  "name": "HA Advanced Timer & Calendar",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2026.0.0",
  "frontend_javascript_modules": [
    "www/atc-timer-card.js",
    "www/atc-reminder-card.js",
    "www/atc-status-card.js"
  ]
}
```

### 13.2 manifest.json (custom_components/advanced_timer_calendar/)

```json
{
  "domain": "advanced_timer_calendar",
  "name": "Advanced Timer & Calendar",
  "version": "1.0.0",
  "documentation": "https://github.com/northpower25/HA-Advanced-Timer-and-Calendar",
  "issue_tracker": "https://github.com/northpower25/HA-Advanced-Timer-and-Calendar/issues",
  "requirements": [],
  "dependencies": [],
  "codeowners": ["@northpower25"],
  "config_flow": true,
  "iot_class": "local_push",
  "homeassistant": "2026.0.0"
}
```

> **Hinweis zu Abhängigkeiten**: Es werden ausschließlich HA-interne Mittel sowie ggf. mitgelieferte Bibliotheken verwendet. Keine externen PyPI-Pakete die separat installiert werden müssen.

### 13.3 Verzeichnisstruktur (HACS-konform)

```
HA-Advanced-Timer-and-Calendar/          ← GitHub Repo Root
├── hacs.json                            ← HACS-Manifest
├── README.md
├── custom_components/
│   └── advanced_timer_calendar/         ← HA Custom Component
│       ├── manifest.json
│       ├── __init__.py
│       └── ...
├── www/                                 ← Lovelace Custom Cards
│   ├── atc-timer-card.js
│   ├── atc-reminder-card.js
│   └── atc-status-card.js
└── dashboard/
    └── atc_dashboard.yaml               ← Standard-Dashboard
```

---

## 14. Bidirektionale Kalenderanbindung (Microsoft 365 / Google / Apple)

### 14.1 Überblick & unterstützte Provider

| Provider | Protokoll / API | Authentifizierung |
|----------|----------------|-------------------|
| Microsoft 365 / Outlook | Microsoft Graph API (REST) | OAuth2 – Device Code Flow oder Authorization Code Flow mit PKCE |
| Google Calendar | Google Calendar API v3 (REST) | OAuth2 – Authorization Code Flow mit PKCE |
| Apple iCloud Calendar | CalDAV (RFC 4791) | App-spezifisches Passwort (Apple-ID + iCloud Passwort-Alternative) |
| Exchange Server (On-Premise) | EWS (Exchange Web Services) oder CalDAV | NTLM / Basic Auth / Modern Auth |

Mehrere Accounts desselben oder verschiedener Provider werden vollständig unterstützt. Jeder Account ist unabhängig konfigurierbar.

### 14.2 Architektur: Externe Kalender-Engine

```
external_calendars/
├── base.py              AbstractCalendarProvider
│                         – authenticate()
│                         – list_calendars()
│                         – get_events(calendar_id, start, end)
│                         – create_event(calendar_id, event)
│                         – update_event(calendar_id, event_id, changes)
│                         – delete_event(calendar_id, event_id)
│                         – subscribe_push(calendar_id, callback_url)  # optional
│
├── microsoft.py         MicrosoftCalendarProvider
│                         – Graph API: /me/calendars, /me/events
│                         – Delta-Query für inkrementelle Sync
│                         – Microsoft Graph Webhooks (Change Notifications)
│
├── google.py            GoogleCalendarProvider
│                         – Google Calendar API v3
│                         – sync_token für inkrementelle Sync
│                         – Google Push Notifications (Webhook)
│
├── apple.py             AppleCalendarProvider
│                         – CalDAV via caldav-Bibliothek
│                         – CTags / ETags für inkrementelle Sync
│                         – Kein Push, nur Polling
│
├── sync_engine.py       SyncEngine
│                         – Verwaltung aller Accounts und deren Zeitpläne
│                         – Inkrementelle Sync (Delta/ETag-basiert)
│                         – Konfliktlösungsstrategie (konfigurierbar)
│                         – Schreibt in HA Storage & externe Kalender
│
├── trigger_processor.py CalendarTriggerProcessor
│                         – Überwacht eingehende Events nach Stichwörtern/Mustern
│                         – Berechnet Vorlaufzeit und plant HA-Trigger
│                         – Löst HA-Automations-Actions aus
│
└── oauth_handler.py     OAuthHandler
                          – Device Code Flow (Microsoft)
                          – Authorization Code + PKCE (Google, Microsoft)
                          – Token-Refresh automatisch
                          – Tokens verschlüsselt in HA Storage
```

### 14.3 Datenmodell: Kalender-Account

```json
{
  "id": "uuid",
  "provider": "microsoft | google | apple | exchange",
  "display_name": "Max Mustermann – Arbeit",
  "owner_name": "Max Mustermann",
  "credentials": {
    "access_token": "...(verschlüsselt)...",
    "refresh_token": "...(verschlüsselt)...",
    "token_expiry": "2026-04-01T10:00:00Z",
    "scope": ["Calendars.ReadWrite"]
  },
  "sync_interval_minutes": 10,
  "last_sync": "2026-03-29T15:00:00Z",
  "calendars": [
    {
      "remote_id": "AQMkAD...",
      "name": "Kalender",
      "color": "#0078d4",
      "sync_enabled": true,
      "sync_direction": "bidirectional",
      "ha_entity_id": "calendar.atc_ext_max_arbeit_kalender",
      "delta_token": "...",
      "read_only": false
    }
  ]
}
```

### 14.4 Datenmodell: Kalender-Trigger (Inbound → HA)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `id` | UUID | Eindeutige ID |
| `name` | string | Anzeigename des Triggers |
| `enabled` | bool | Aktiv/Inaktiv |
| `account_id` | UUID | Verknüpfter Kalender-Account |
| `calendar_ids` | list[str] | Zu überwachende Kalender (leer = alle) |
| `keyword_filter` | string\|None | Stichwort im Titel/Beschreibung (z.B. `"#smarthome"`) |
| `tag_filter` | list[str] | Kategorien/Tags im Kalender-Termin |
| `lead_time_minutes` | int | Vorlaufzeit vor Terminbeginn (0 = beim Start) |
| `also_at_end` | bool | Auch bei Terminende auslösen |
| `actions` | list | Auszuführende HA-Aktionen |
| `conditions` | list | Zusätzliche HA-Bedingungen |
| `entity_target` | string\|None | Direkt zu steuernde Entität (Schnellkonfiguration) |
| `notification` | dict\|None | Benachrichtigungsconfig |

**Beispiel-Konfiguration:**
```
Name: „Homeoffice-Modus aktivieren"
Account: Max Arbeit (Microsoft 365)
Kalender: Kalender (Hauptkalender)
Stichwort: „Homeoffice" (im Titel)
Vorlaufzeit: 10 Minuten
Aktion 1: light.office_lamp → turn_on, brightness 80%
Aktion 2: switch.monitor → turn_on
Aktion 3: climate.office → set_temperature 21°C
Auch bei Terminende: Ja → Alle Geräte ausschalten
```

### 14.5 Datenmodell: Ausgehende Sync-Konfiguration (HA → Externer Kalender)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `outbound_account_id` | UUID | Ziel-Account für ausgehende Sync |
| `outbound_calendar_id` | string | Ziel-Kalender-ID |
| `sync_timers` | bool | Timer-Trigger als externe Termine exportieren |
| `sync_reminders` | bool | Reminder als externe Termine exportieren |
| `sync_prefix` | string | Präfix für exportierte Termine (z.B. `"[HA]"`) |
| `include_description` | bool | Timer-Details in Terminbeschreibung schreiben |

### 14.6 Sync-Engine: Technische Details

#### Inkrementelle Synchronisation
- **Microsoft Graph**: `delta()`-Endpunkt liefert nur geänderte/neue/gelöschte Events seit letztem Sync → `deltaLink` Token wird gespeichert
- **Google Calendar**: `syncToken` nach jeder Sync-Antwort gespeichert → nächste Abfrage liefert nur Änderungen
- **Apple CalDAV**: `CTag` des Kalenders auf Änderungen prüfen, dann ETags einzelner Events vergleichen

#### Push-Benachrichtigungen (Near-Realtime)
- **Microsoft Graph Webhooks**: Subscription auf `/me/events` → Callback-URL (HA-interner Webhook-Endpoint) → sofortige Benachrichtigung bei neuen/geänderten Terminen
- **Google Push Notifications**: Channel auf Google Calendar API → `X-Goog-Channel-Expiration` beachten (max. 7 Tage, automatische Erneuerung)
- **Apple CalDAV**: Kein Push-Support → Polling (konfigurierbares Intervall, Standard: 10 Minuten)

#### Konfliktlösung (konfigurierbar pro Account)
| Strategie | Beschreibung |
|-----------|-------------|
| `ha_wins` | Bei Konflikt überschreibt HA-Version die externe |
| `remote_wins` | Bei Konflikt überschreibt externe Version die HA-Version |
| `newest_wins` | Neuerer `last_modified`-Zeitstempel gewinnt |
| `manual` | Konflikt wird als Sensor-State gemeldet, User entscheidet via Service-Aufruf |

#### Token-Management
- Access Token wird vor jedem API-Aufruf auf Gültigkeit geprüft
- Automatischer Refresh via Refresh Token
- Bei fehlgeschlagenem Refresh: Sensor-State auf `reauth_required` setzen und Benachrichtigung senden
- Tokens AES-256-verschlüsselt in der HA Storage API gespeichert (Schlüssel aus `HA secret`)

### 14.7 HA-Entitäten für externe Kalender

| Entity | Typ | Beschreibung |
|--------|-----|-------------|
| `calendar.atc_ext_<account>_<kalender>` | Calendar | Externer Kalender als HA-CalendarEntity (read/write) |
| `sensor.atc_ext_<account>_sync_status` | Sensor | `ok`, `syncing`, `error`, `reauth_required` |
| `sensor.atc_ext_<account>_last_sync` | Sensor | Zeitstempel letzter erfolgreicher Sync |
| `sensor.atc_ext_<account>_next_event` | Sensor | Nächster bevorstehender Termin (Titel + Startzeit) |
| `binary_sensor.atc_ext_<account>_in_meeting` | Binary Sensor | `on` wenn gerade ein Termin läuft |

### 14.8 Config Flow: Kalender-Account hinzufügen (Schritt für Schritt)

```
1. Provider wählen: [Microsoft 365] [Google] [Apple iCloud] [Exchange]

── Microsoft 365 ──────────────────────────────────────────────
2. Anzeigename eingeben: „Privat / Arbeit / Familie"
3. Device Code Flow starten:
   → Code wird angezeigt: „Gehe zu https://microsoft.com/devicelogin und gib ein: ABCD-EFGH"
   → Integration wartet auf Authentifizierung (Timeout: 5 Minuten)
   → Nach Erfolg: „✅ Erfolgreich authentifiziert als max@contoso.com"
4. Kalender-Liste wird geladen → Benutzer wählt Kalender aus
5. Pro Kalender: Sync-Richtung (Bidirektional / Nur eingehend / Nur ausgehend)

── Google Calendar ────────────────────────────────────────────
2. Anzeigename eingeben
3. OAuth2 Authorization URL wird generiert:
   → HA öffnet HA-internen Callback-Endpoint auf Port 8123
   → Benutzer öffnet URL im Browser → meldet sich bei Google an → erteilt Berechtigung
   → Nach Redirect: Token automatisch gespeichert
4. Kalender-Liste → Auswahl → Sync-Richtung

── Apple iCloud ───────────────────────────────────────────────
2. Anzeigename eingeben
3. Apple-ID (E-Mail) eingeben
4. App-spezifisches Passwort eingeben (Hinweis: https://appleid.apple.com → Sicherheit)
5. CalDAV-Server wird ermittelt (automatisch via DNS-SRV-Record)
6. Kalender-Liste → Auswahl → Sync-Richtung
```

### 14.9 Abgrenzung zu bestehenden HA-Integrationen

| Integration | Unterschied zu ATC |
|-------------|-------------------|
| HA `google` (Google Calendar) | Nur Lesezugriff, keine Trigger-Verarbeitung, kein Outbound-Sync |
| HA `microsoft365` (über HACS) | Kein direkter Timer-/Reminder-Sync, keine Keyword-Trigger |
| HA native CalDAV | Nur Lesezugriff, kein Schreiben, keine Trigger |
| ATC (dieses Konzept) | Vollbidirektional, Keyword-Trigger, Multi-Account, tief in Timer/Reminder integriert |

---

## 15. Weitere Microsoft Office / Produktivitäts-Integrationen

### 15.1 Microsoft Teams – Präsenz & Meeting-Steuerung

**Szenario**: Wenn der Nutzer in einem Teams-Meeting ist → Bürolicht dimmen, „Bitte nicht stören"-LED einschalten, Türklingel-Benachrichtigungen stumm schalten.

**Technische Umsetzung**:
- Microsoft Graph API: `GET /me/presence` – liefert Anwesenheitsstatus (`Available`, `Busy`, `InACall`, `InAMeeting`, `DoNotDisturb`, `Away`, `Offline`)
- Polling alle 60 Sekunden oder Graph Change Notifications auf `/communications/presences`
- HA-Entitäten:
  - `sensor.atc_teams_presence_<name>` → Wert: `available`, `busy`, `in_meeting`, `dnd`, `away`, `offline`
  - `binary_sensor.atc_teams_in_meeting_<name>` → `on` wenn in Meeting
- HA-Automations können auf Statuswechsel reagieren

**Mögliche Automatisierungen**:
```
Meeting beginnt (InAMeeting):
  → light.office → dimmen auf 30%
  → switch.dnd_light → ON
  → notify.family → „Max ist im Meeting bis 15:00"

Meeting endet (Available):
  → light.office → 100%
  → switch.dnd_light → OFF
```

### 15.2 Microsoft To Do / Planner

**Microsoft To Do**:
- REST API: Aufgabenlisten lesen/schreiben (`/me/todo/lists/{listId}/tasks`)
- Bidirektionaler Sync mit HA ToDo-Plattform
- Fällige Aufgaben als HA-Reminder → Benachrichtigung via Telegram
- Neue Aufgaben aus HA heraus erstellen (via HA Dashboard oder Service)

**Microsoft Planner** (Team-Aufgaben):
- Aufgaben-Status als HA-Sensor (z.B. Projektfortschritt)
- Neue Aufgaben bei bestimmten HA-Events erstellen (z.B. „Filter wechseln" wenn Luftqualitäts-Sensor Grenzwert überschreitet)

### 15.3 Microsoft Outlook – E-Mail-Trigger

**Szenarien**:
- E-Mail mit Betreff-Stichwort (z.B. „Paket angekommen") → HA-Aktion auslösen (Benachrichtigung, Klingel-Simulation)
- E-Mail-Benachrichtigungen bei HA-Events (z.B. Alarmmeldung) → E-Mail über Graph API senden
- Ungelesene E-Mails als HA-Sensor (Badge-Counter)

**Technische Umsetzung**:
- Graph API: `/me/messages` mit `$filter` und `$select`
- Graph Webhooks auf Posteingang für Near-Realtime
- Service `atc.send_email`: E-Mail über konfigurierten Outlook-Account senden

### 15.4 Microsoft OneDrive / SharePoint

**Szenarien**:
- Automatisches Backup von HA-Konfiguration auf OneDrive (täglich/wöchentlich)
- Export von Timer/Reminder-Daten auf OneDrive
- Datei-Trigger: Neue Datei in OneDrive-Ordner → HA-Aktion (z.B. Bild von Türkamera → automatisch hochladen)

**Technische Umsetzung**:
- Graph API: `/me/drive/root:/Pfad:/children` für Datei-Upload
- Service `atc.backup_to_onedrive`: Manuelles oder automatisches Backup
- Webhook auf OneDrive-Ordner für Datei-Trigger

### 15.5 Google Workspace – Erweiterungen

**Google Tasks**:
- Bidirektionaler Sync mit HA ToDo-Plattform (analog Microsoft To Do)
- Aufgaben als HA-Reminder, Erledigung aus HA heraus

**Google Meet – Präsenz** (via Google Calendar):
- Meeting-Status aus laufenden Google Calendar-Ereignissen ableiten
- `binary_sensor.atc_google_in_meeting_<name>` wenn Termin mit Meet-Link aktiv ist

**Google Gmail – E-Mail-Trigger**:
- Gmail API (Pub/Sub Push) für E-Mail-Trigger
- Service `atc.send_gmail`: E-Mail senden via Gmail API

### 15.6 Apple-Erweiterungen

**Apple Reminders (via CalDAV-Erweiterung)**:
- Teilweise über CalDAV VTODO-Komponenten zugänglich
- Sync mit HA ToDo-Plattform

**iCloud Drive**:
- Kein offizielles API – über Drittanbieter-Bibliotheken eingeschränkt möglich; nicht empfohlen für produktiven Einsatz

### 15.7 Übersichts-Tabelle: Integrations-Roadmap

| Feature | Provider | Priorität | Komplexität | Phase |
|---------|----------|-----------|-------------|-------|
| Kalender-Sync bidirektional | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | Hoch | 3 |
| Kalender-Trigger (Keyword) | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | Mittel | 3 |
| Teams-Präsenz-Sensor | Microsoft | ⭐⭐⭐⭐ | Mittel | 4 |
| To Do / Tasks Sync | Microsoft / Google | ⭐⭐⭐⭐ | Mittel | 4 |
| E-Mail-Trigger (Inbox) | Microsoft / Google | ⭐⭐⭐ | Mittel | 4 |
| E-Mail senden (Service) | Microsoft / Google | ⭐⭐⭐ | Niedrig | 4 |
| OneDrive Backup | Microsoft | ⭐⭐⭐ | Niedrig | 4 |
| Planner-Aufgaben | Microsoft | ⭐⭐ | Mittel | 5 |
| SharePoint-Datei-Trigger | Microsoft | ⭐⭐ | Hoch | 5 |
| iCloud Drive | Apple | ⭐ | Sehr hoch | – |

---
