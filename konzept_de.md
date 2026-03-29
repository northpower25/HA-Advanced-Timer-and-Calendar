# Konzept: HA Advanced Timer & Calendar

## 1. Überblick & Ziele

Eine Custom Component für Home Assistant, die folgende Kernbereiche abdeckt:

- **Timer / Scheduler**: Steuerung von Entitäten (Switches, Lights, etc.) nach Zeitplan
- **Reminder / Kalender**: Erinnerungen, Termine, Jahrestage, ToDos
- **Telegram-Integration**: Benachrichtigungen und Bot-Steuerung
- **Persistenz**: Alle Daten überleben HA-Neustarts
- **Laienfreundlichkeit**: Vollständige Konfiguration über die HA-UI (Config Flow + Options Flow)

---

## 2. Architektur

### 2.1 Komponentenstruktur

```
custom_components/advanced_timer_calendar/
├── __init__.py              # Setup, Coordinator-Start
├── manifest.json            # Metadaten, Abhängigkeiten
├── config_flow.py           # Einrichtungsassistent (UI)
├── options_flow.py          # Nachträgliche Einstellungen
├── const.py                 # Konstanten, Enums
├── coordinator.py           # Zentraler DataUpdateCoordinator
├── storage.py               # Persistenz via HA Storage API
├── scheduler.py             # Timer-Logik & Scheduling-Engine
├── calendar.py              # Calendar-Plattform (CalendarEntity)
├── sensor.py                # Sensor-Plattform (Status, nächster Trigger)
├── switch.py                # Switch-Plattform (Timer ein/aus)
├── services.yaml            # HA-Service-Definitionen
├── services.py              # Service-Handler
├── telegram_bot.py          # Telegram-Benachrichtigungs- & Steuerungsmodul
├── translations/
│   ├── de.json
│   └── en.json
└── strings.json
```

### 2.2 Datenhaltung

**HA Storage API** (`.storage/advanced_timer_calendar`) – JSON-Datei, die bei jedem Schreiben gespeichert wird. Kein Verlust bei Neustart.

Datenstruktur (vereinfacht):

```json
{
  "version": 1,
  "timers": [ { "...Timer-Objekt..." } ],
  "reminders": [ { "...Reminder-Objekt..." } ],
  "settings": { "...globale Einstellungen..." }
}
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

**Modus A – Eigenständig** (einfach): Direkte Eingabe von Bot-Token + Chat-ID im Config Flow → die Integration sendet selbst Nachrichten über die Telegram Bot API.

**Modus B – HA Telegram Bot** (fortgeschritten): Nutzung der bestehenden `telegram_bot`-Integration in HA als Notification-Service.

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

### 5.3 Bot-Steuerung (Modus B)

Über Telegram-Befehle Timer steuern:

| Befehl | Funktion |
|--------|---------|
| `/timer list` | Alle Timer anzeigen |
| `/timer pause Garten` | Timer pausieren |
| `/timer resume Garten` | Timer fortsetzen |
| `/timer next Garten` | Nächste Ausführung anzeigen |
| `/reminder list` | Anstehende Reminder |
| `/reminder add ...` | Schnell-Reminder erstellen |
| `/status` | Systemüberblick |

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

---

## 8. Config Flow (Einrichtungsassistent)

### Schritt 1 – Allgemein
- Name der Integration-Instanz

### Schritt 2 – Telegram (optional)
- Modus: "Kein Telegram", "Eigener Bot", "HA Telegram Bot"
- Bei "Eigener Bot": Bot-Token, Chat-ID, Test-Nachricht senden
- Bei "HA Telegram Bot": Auswahl des vorhandenen Notification-Services

### Schritt 3 – Standardeinstellungen
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

### 9.2 Lovelace Cards (Phase 2, optional)
Für maximale Benutzerfreundlichkeit könnten Custom Cards entwickelt werden:

- **ATC Timer Card**: Übersicht aller Timer, schnelles An/Aus, nächste Ausführung
- **ATC Reminder Card**: Kalenderansicht der nächsten Termine
- **ATC Quick Reminder Card**: Schnelles Erstellen von Erinnerungen

---

## 10. Technische Entscheidungen & offene Fragen

### Offene Fragen / Entscheidungsbedarf

1. **Mindest-HA-Version**: Ab welcher HA-Version soll die Integration funktionieren? Empfehlung: 2023.9+ (stabile Calendar & ToDo API)
2. **Mehrere Instanzen**: Soll man die Integration mehrfach installieren können (z.B. "Garten", "Haus")? Oder eine zentrale Instanz mit Gruppen/Tags?
3. **Abhängigkeiten**: Nutzung von `croniter` (PyPI) für Cron-Ausdrücke und `python-telegram-bot` für den eigenständigen Modus – oder nur HA-interne Mittel?
4. **Migrations-Strategie**: Wie soll die Storage-Schema-Migration bei Updates aussehen (Versionierung im Storage-File)?
5. **Telegram Bot Commands**: Soll der Bot interaktiv sein (Inline-Keyboards für Bestätigung) oder nur einfache Text-Befehle?
6. **Bewässerungs-Sensor-Logik**: Soll es ein dediziertes "Bewässerungsprofil"-Feature geben oder reicht die generische Bedingungslogik?
7. **Lovelace Cards**: In Phase 1 integrieren oder erst in Phase 2? Erhöht Komplexität deutlich.
8. **HACS-Kompatibilität**: Von Anfang an HACS-konform entwickeln (empfohlen) – benötigt spezifische `hacs.json` Datei.

### Empfohlene Designentscheidungen

- **Storage statt SQLite**: HA Storage API ist die idiomatische Lösung, kein eigenes Datenbankschema
- **DataUpdateCoordinator**: Zentrales State-Management, alle Plattformen subscriben darauf
- **asyncio nativ**: Keine blocking calls, alles async
- **HACS von Anfang an**: Ermöglicht einfache Distribution und Updates für Laien

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
- Persistenz & Storage
- Scheduler-Engine (`daily`, `weekdays`, `interval`, `yearly`, `once`)
- Aktionen (`turn_on`, `turn_off`, Dauer)
- Bedingungen (Entitätszustand, Template)
- HA-Entitäten (Switch, Sensor)
- Config Flow (ohne Telegram)
- Kalender-Plattform
- Services

### Phase 2 – Telegram & Reminder
- Telegram Modus A (eigenständig)
- Telegram Modus B (HA-Integration)
- Reminder/Kalender-Typen (Jahrestage, ToDos)
- HA ToDo-Plattform-Integration
- Sunrise/Sunset-Trigger

### Phase 3 – Komfort & Erweiterungen
- Lovelace Cards
- Smart Watering Algorithmus
- Timer-Templates
- Import/Export
- Bot Inline-Keyboards
- Statistiken

---

## 13. Offene Punkte für Klärung

Bevor mit der Umsetzung begonnen wird, bitte folgende Punkte entscheiden:

1. **Welche HA-Mindestversion** soll unterstützt werden?
2. **Sollen externe Python-Bibliotheken** (`croniter`, `python-telegram-bot`) verwendet werden, oder soll die Integration möglichst ohne externe Abhängigkeiten auskommen?
3. **Cron-Ausdrücke** für fortgeschrittene Nutzer gewünscht, oder reichen die definierten Schedule-Typen?
4. **Mehrinstanzen-Fähigkeit** (`config_entries`) von Anfang an, oder Single-Instance?
5. **Phase 1 Scope bestätigen**: Ist das MVP sinnvoll abgegrenzt, oder sollen bestimmte Features vorgezogen/verschoben werden?
6. **Telegram-Priorität**: Soll Telegram bereits in Phase 1 dabei sein (da es ein Kernanforderung ist)?
7. **Sprache der UI-Texte**: Deutsch und Englisch von Anfang an (`translations/de.json` + `en.json`)?
