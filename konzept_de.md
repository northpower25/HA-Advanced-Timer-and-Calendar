# Konzept: HA Advanced Timer & Calendar

## 1. Überblick & Ziele

Eine Custom Component für Home Assistant, die folgende Kernbereiche abdeckt:

- **Timer / Scheduler**: Steuerung von Entitäten (Switches, Lights, etc.) nach Zeitplan
- **Reminder / Kalender**: Erinnerungen, Termine, Jahrestage, ToDos
- **Telegram-Integration**: Benachrichtigungen und bidirektionale Bot-Steuerung (interaktiv wenn HA Telegram Bot vorhanden)
- **Sprachbenachrichtigungen**: Vorgelesene Timer- und Reminder-Benachrichtigungen via Alexa Media Player, Google Home/Cast, Sonos oder beliebigem HA-TTS-kompatiblem Media Player – mit vordefinierten und frei konfigurierbaren Sprachtexten
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
├── voice_notifications.py   # Sprachbenachrichtigungs-Modul
│                            # (Alexa Media Player, Google Home/Cast, Sonos, HA TTS)
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

Bedingungen blockieren den Timer-Trigger wenn nicht erfüllt. Mehrere Bedingungen können über AND/OR-Logik verknüpft werden.

- **Entitätszustand**: z.B. `sensor.rain_sensor == 'raining'` → Timer überspringen
- **Zeitfenster**: Nur ausführen wenn zwischen 06:00–20:00
- **Numerischer Schwellwert**: z.B. `sensor.soil_moisture < 30` (kleiner als / größer als Wert)
- **Numerischer Bereich (von/bis)**: z.B. `sensor.outdoor_temperature` zwischen `10°C` und `25°C`
- **Template**: Beliebiges HA-Template

#### Bedingungsgruppen & Verschachtelung

Bedingungen werden als **Baumstruktur** gespeichert, die beliebig tiefe Verschachtelungen ermöglicht – z.B. `(A AND B) OR C`. Jeder Knoten im Baum ist entweder eine **Bedingungsgruppe** (mit einem `operator` und einer Liste von Kind-Knoten) oder ein **Bedingungs-Item** (Blattknoten mit konkreter Prüflogik).

##### Bedingungsgruppe (ConditionGroup)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `type` | `"group"` | Kennzeichnet diesen Knoten als Gruppe |
| `operator` | enum | `"and"` / `"or"` – Verknüpfung aller Kind-Knoten dieser Gruppe |
| `conditions` | list | Liste von Kind-Knoten (ConditionGroup oder ConditionItem) |

##### Bedingungs-Item (ConditionItem)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `type` | `"item"` | Kennzeichnet diesen Knoten als Blattknoten |
| `entity_id` | string | Zu prüfende Entität |
| `condition_type` | enum | `state`, `numeric_below`, `numeric_above`, `numeric_between`, `template` |
| `value` | any\|None | Vergleichswert (bei `state`, `numeric_below`, `numeric_above`) |
| `min_value` | float\|None | Unterer Grenzwert (nur bei `numeric_between`) |
| `max_value` | float\|None | Oberer Grenzwert (nur bei `numeric_between`) |
| `template` | string\|None | HA-Template-Ausdruck (nur bei `template`) |
| `hold_seconds` | int\|None | Haltezeit in Sekunden (0 = sofortige Auslösung, `None` = kein Hold) |

**Beispiel – einfaches AND (flach):**
```yaml
conditions:
  type: group
  operator: and
  conditions:
    - type: item
      entity_id: sensor.rain_sensor
      condition_type: state
      value: "dry"
    - type: item
      entity_id: sensor.soil_moisture
      condition_type: numeric_below
      value: 30
```

**Beispiel – verschachteltes `(A AND B) OR C`:**
```yaml
conditions:
  type: group
  operator: or
  conditions:
    - type: group
      operator: and
      conditions:
        - type: item
          entity_id: sensor.outdoor_temperature   # A
          condition_type: numeric_between
          min_value: 10
          max_value: 30
        - type: item
          entity_id: sensor.rain_sensor           # B
          condition_type: state
          value: "dry"
    - type: item
      entity_id: input_boolean.manual_override    # C
      condition_type: state
      value: "on"
```

**UI-Darstellung**: Im ATC-Frontend werden Bedingungsgruppen als visuell eingerückte Blöcke mit einem AND/OR-Selektor dargestellt. Über Schaltflächen können neue Einzelbedingungen oder Untergruppen hinzugefügt werden.

#### 3.4.1 Haltezeit (Hold Timer)

Jedes Bedingungs-Item kann mit einer **Haltezeit** (`hold_seconds`) versehen werden: Der gemessene Zustand muss für mindestens die angegebene Dauer kontinuierlich erfüllt sein, bevor das Timer-Event ausgelöst wird. Dies verhindert Fehlauslösungen durch kurzzeitige Messschwankungen (z.B. kurzzeitige Temperaturschwankungen).

Das Feld `hold_seconds` ist direkt im `ConditionItem` enthalten (siehe Tabelle oben).

**Beispiel:** Außentemperatur unter 0°C **für mindestens 10 Minuten** → Frostschutz aktivieren (`hold_seconds: 600`).

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

## 5. Benachrichtigungen & Telegram-Integration

### 5.0 Benachrichtigungskanäle

Pro Timer/Termin können ein oder mehrere Benachrichtigungskanäle unabhängig aktiviert werden:

| Kanal | Beschreibung |
|-------|-------------|
| **Telegram (Modus A)** | Direkt via Bot-Token – nur ausgehende Nachrichten |
| **Telegram (Modus B)** | Via HA `telegram_bot` – bidirektional & interaktiv mit Inline-Keyboards |
| **HA Notify** | Beliebiger HA-Benachrichtigungs-Service (z.B. `notify.mobile_app_iphone`, `notify.pushover`, E-Mail-Notify, etc.) |
| **Sprachbenachrichtigung** | Vorgelesene Nachrichten auf Alexa-, Google Home/Cast-, Sonos- oder anderen HA-TTS-fähigen Geräten |

Die Kanäle können kombiniert werden, z.B. Telegram **und** HA Notify **und** Sprachbenachrichtigung gleichzeitig für denselben Timer.

### 5.1 Betriebsmodi (Telegram)

**Modus A – Eigenständig** (einfach): Direkte Eingabe von Bot-Token + Chat-ID im Config Flow → die Integration sendet selbst Nachrichten über die Telegram Bot API. Nur ausgehende Benachrichtigungen, keine eingehenden Befehle.

**Modus B – HA Telegram Bot** (fortgeschritten, empfohlen): Nutzung der bestehenden `telegram_bot`-Integration in HA. Wenn diese vorhanden ist, wird **bidirektionale und interaktive** Kommunikation aktiviert:
- Ausgehend: Nachrichten und Inline-Keyboards über `notify.<telegram_service>`
- Eingehend: Befehle und Callback-Antworten über HA-Events (`telegram_command`, `telegram_callback`)
- Interaktive Inline-Keyboards für Bestätigungen, Auswahlen und Statusabfragen

### 5.2 Benachrichtigungszeitpunkte

Für jeden Timer/Termin können **bis zu drei Benachrichtigungszeitpunkte** unabhängig aktiviert/deaktiviert werden:

| # | Zeitpunkt | Konfiguration |
|---|-----------|--------------|
| **1** | **Vorab** – bevor der Timer/Termin aktiv wird | Zeitraum in Minuten, Stunden, Tagen oder Wochen vor Auslösung |
| **2** | **Nachher** – nachdem der Timer/Termin aktiv wurde | Zeitraum in Minuten, Stunden, Tagen oder Wochen nach Auslösung |
| **3** | **Abschluss** – wenn das Timer-Event abgeschlossen und der Timer zurückgesetzt wurde | Keine weitere Zeitkonfiguration nötig |

**Datenmodell Benachrichtigungs-Config (`notification`):**

```json
{
  "channels": ["telegram", "ha_notify", "voice"],
  "ha_notify_service": "notify.mobile_app_iphone",
  "voice": {
    "enabled": true,
    "provider": "alexa_media_player",
    "media_player_entity": "media_player.echo_dot_kueche",
    "volume": 0.6,
    "tts_engine": null,
    "language": "de-DE"
  },
  "notify_before": {
    "enabled": true,
    "value": 30,
    "unit": "minutes"
  },
  "notify_after": {
    "enabled": true,
    "value": 5,
    "unit": "minutes"
  },
  "notify_on_reset": true,
  "templates": {
    "before": "⏰ {{ name }} startet in {{ time_until }}.",
    "after": "✅ {{ name }} wurde gestartet.",
    "reset": "🔄 {{ name }} wurde abgeschlossen und zurückgesetzt.",
    "skipped": "⏭ {{ name }} wurde übersprungen ({{ reason }}).",
    "voice_before": "{{ name }} startet in {{ time_until }}.",
    "voice_after": "{{ name }} wurde gestartet.",
    "voice_reset": "{{ name }} wurde abgeschlossen.",
    "voice_skipped": "{{ name }} wurde übersprungen."
  }
}
```

**Unterstützte Zeiteinheiten (`unit`):** `minutes`, `hours`, `days`, `weeks`

**Trigger-Anlässe:**

- Timer-Trigger Beginn (vorab & nachher)
- Timer-Trigger Ende / Zurücksetzen (Abschluss-Benachrichtigung)
- Bedingung verhindert Ausführung ("Bewässerung übersprungen – Regen erkannt")
- Reminder/Termin kurz vor Fälligkeit
- ToDo fällig
- Fehler / Timer deaktiviert

### 5.3 Benachrichtigungstexte & Vorlagen

Die Texte für alle Benachrichtigungszeitpunkte werden **automatisch vorgeschlagen** und können pro Timer/Termin individuell angepasst werden. Standard-Vorlagen werden in `translations/de.json` und `translations/en.json` definiert.

**Standard-Vorlagen (Beispiele):**

| Zeitpunkt | Standard-Text |
|-----------|--------------|
| Vor Auslösung | `⏰ [Timer-Name] startet in [Zeitraum].` |
| Nach Auslösung | `✅ [Timer-Name] wurde gestartet. Dauer: [Dauer] min.` |
| Abschluss/Reset | `🔄 [Timer-Name] wurde abgeschlossen und zurückgesetzt.` |
| Übersprungen | `⏭ [Timer-Name] wurde übersprungen. Grund: [Bedingung].` |
| Reminder | `🔔 Erinnerung: [Titel] in [Zeitraum].` |

**Template-Variablen** (verwendbar in allen Texten): `{{ name }}`, `{{ time_until }}`, `{{ duration }}`, `{{ reason }}`, `{{ next_run }}`, `{{ entity_states }}`.

Im ATC-UI werden die Vorlagen bei der Konfiguration eines Timers/Termins angezeigt, können direkt bearbeitet und vor dem Speichern getestet werden.

### 5.4 Bot-Steuerung (Modus B – HA Telegram Bot)

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

## 5.5 Sprachbenachrichtigungen (Voice Notifications)

ATC unterstützt das Vorlesen von Timer- und Reminder-Benachrichtigungen auf Smart-Speakern und anderen Audiogeräten. Die Sprachbenachrichtigung ist ein eigenständiger, kombinierbarer Kanal (zusätzlich zu Telegram und HA Notify).

### Unterstützte Integrationen & Voraussetzungen

#### 🔔 Alexa Media Player (empfohlen für Amazon Echo-Geräte)

> ⚠️ **Installation erforderlich**: Die [Alexa Media Player](https://github.com/alandtse/alexa_media_player) Integration muss separat über **HACS** installiert werden. Sie ist **nicht** Bestandteil von Home Assistant Core.
> Installations-Link: **https://github.com/alandtse/alexa_media_player**

- Unterstützte Geräte: Amazon Echo, Echo Dot, Echo Show, Echo Studio, Fire TV (mit Alexa)
- Funktionsprinzip: ATC ruft den Notify-Service `notify.alexa_media_<gerätename>` auf und übermittelt den Nachrichtentext als `announce`-Typ
- Die Nachricht wird auf dem gewählten Alexa-Gerät laut vorgelesen, ohne den aktuellen Medieninhalt dauerhaft zu unterbrechen
- Unterstützt auch Gruppen (mehrere Echo-Geräte gleichzeitig ansprechen)
- Lautstärke: Über das `data`-Feld der Notify-Service-Payload steuerbar

**Beispiel-Service-Aufruf (intern von ATC generiert):**
```yaml
service: notify.alexa_media_echo_dot_kueche
data:
  message: "Bewässerung Zone 1 startet in 5 Minuten."
  data:
    type: announce
    method: all
```

**Voraussetzungen:**
1. Alexa Media Player via HACS installieren: https://github.com/alandtse/alexa_media_player
2. Amazon-Konto in der Alexa Media Player Integration anmelden
3. Echo-Geräte werden automatisch als `media_player.echo_*`-Entitäten erkannt

---

#### 🏠 Google Home / Google Cast (nativ in HA)

> ✅ **Keine zusätzliche Installation nötig** – Die Google Cast Integration ist Bestandteil von Home Assistant Core.

- Unterstützte Geräte: Google Home, Google Home Mini/Nest Mini, Nest Hub, Nest Hub Max, Chromecast Audio, jedes Gerät mit Google Cast-Unterstützung
- Funktionsprinzip: ATC nutzt den HA-eigenen `tts.speak`-Service mit dem Google Cast `media_player`
- TTS-Engine: Konfigurierbar (Standard: `tts.google_translate_say` oder `tts.cloud_say` via HA Cloud)

**Beispiel-Service-Aufruf:**
```yaml
service: tts.speak
data:
  media_player_entity_id: media_player.google_home_wohnzimmer
  message: "Bewässerung Zone 1 startet in 5 Minuten."
  options:
    voice: de-DE-Standard-A
```

---

#### 🎵 Sonos (nativ in HA)

> ✅ **Keine zusätzliche Installation nötig** – Die Sonos Integration ist Bestandteil von Home Assistant Core.

- Unterstützte Geräte: Alle Sonos-Lautsprecher (Era, Move, Roam, One, Five, Arc, Beam, Ray etc.)
- Funktionsprinzip: `tts.speak`-Service mit einem Sonos `media_player`
- TTS-Engine: Konfigurierbar (Piper/lokal, HA Cloud TTS, Google Translate TTS)
- Unterstützt Lautstärke-Steuerung vor/nach der Ansage und Wiederherstellung des vorherigen Zustands

---

#### 🔊 HA TTS + beliebiger Media Player (generisch)

> ✅ **Keine zusätzliche Installation nötig** – Funktioniert mit jedem in HA eingebundenen `media_player`-Gerät.

- Funktionsprinzip: ATC nutzt den `tts.speak`-Service mit der im Config Flow gewählten Media-Player-Entität und TTS-Engine
- Kompatibel mit: VLC Media Player, ESPHome Speaker, Squeezebox/Logitech Media Server, Kodi, und allen anderen HA-`media_player`-Entitäten
- **Verfügbare TTS-Engines (Auswahl):**

| TTS-Engine | Typ | Anforderung | Qualität |
|-----------|-----|-------------|---------|
| **Piper** (lokal) | Lokal | Wyoming-Protokoll / Add-on | ⭐⭐⭐⭐ – Offline, privat, kostenlos |
| **HA Cloud TTS** | Cloud | Nabu Casa-Abonnement | ⭐⭐⭐⭐⭐ – Sehr natürlich (Azure Neural) |
| **Google Translate TTS** | Cloud | Keine (kostenlos) | ⭐⭐⭐ – Einfach, keine Konfiguration nötig |
| **Microsoft Azure TTS** | Cloud | Azure-Konto + API-Key | ⭐⭐⭐⭐⭐ – Sehr natürlich |
| **Amazon Polly** | Cloud | AWS-Konto + API-Key | ⭐⭐⭐⭐ – Natürlich |
| **ElevenLabs** | Cloud | API-Key (kostenpflichtig) | ⭐⭐⭐⭐⭐ – Sehr natürlich |

---

### Konfiguration im Config Flow (Schritt: Sprachbenachrichtigungen)

Im Config Flow von ATC wird Sprachbenachrichtigung als optionaler Schritt angeboten:

```
┌─────────────────────────────────────────────────────────────────┐
│  Sprachbenachrichtigungen (optional)                            │
│                                                                 │
│  Integration / Anbieter:                                        │
│  ○ Alexa Media Player ⚠️ HACS-Installation erforderlich        │
│  ○ Google Home / Google Cast                                    │
│  ○ Sonos                                                        │
│  ○ HA TTS + Media Player (generisch)                           │
│  ○ Kein Sprachkanal                                             │
│                                                                 │
│  [Bei Alexa Media Player:]                                      │
│  Media Player Entität:  [media_player.echo_dot_kueche ▾]       │
│  Lautstärke:            [████░░░░░░] 60%                        │
│  Ansagemodus:           ○ announce  ○ tts                       │
│                                                                 │
│  [Bei Google/Sonos/generisch:]                                  │
│  Media Player Entität:  [media_player.google_home_wohnzimmer ▾]│
│  TTS-Engine:            [tts.cloud_say ▾]                       │
│  Sprache:               [de-DE ▾]                               │
│  Lautstärke:            [████░░░░░░] 60%                        │
│                                                                 │
│  Standard-Sprachvorlagen: (bearbeitbar)                         │
│  Vorab:    "{{ name }} startet in {{ time_until }}."            │
│  Nachher:  "{{ name }} wurde gestartet."                        │
│  Abschluss:"{{ name }} wurde abgeschlossen."                    │
│  Reminder: "Erinnerung: {{ title }} in {{ time_until }}."       │
│                                                                 │
│  [Test-Ansage abspielen]    [Weiter]                            │
└─────────────────────────────────────────────────────────────────┘
```

> ⚠️ **Hinweis bei Alexa Media Player**: Damit diese Funktion genutzt werden kann, muss die [Alexa Media Player](https://github.com/alandtse/alexa_media_player) Integration via HACS installiert und konfiguriert sein. Ohne diese Integration werden Alexa-Geräte nicht als auswählbare Entitäten angezeigt.

---

### Vordefinierte Sprachtexte & Vorlagen

Für jeden Benachrichtigungszeitpunkt existieren separate, TTS-optimierte Sprachtextvorlagen (ohne Emojis, kürzer als schriftliche Texte):

| Zeitpunkt | Vordefinierter Sprachtext |
|-----------|--------------------------|
| Vorab | `{{ name }} startet in {{ time_until }}.` |
| Nach Auslösung | `{{ name }} wurde gestartet. Dauer: {{ duration }} Minuten.` |
| Abschluss/Reset | `{{ name }} wurde abgeschlossen.` |
| Übersprungen | `{{ name }} wurde übersprungen. Grund: {{ reason }}.` |
| Reminder | `Erinnerung: {{ title }} in {{ time_until }}.` |
| Fehler/Deaktiviert | `Timer {{ name }} ist deaktiviert oder hat einen Fehler.` |

Die Vorlagen sind pro Timer/Termin individuell anpassbar. Template-Variablen sind identisch mit denen für schriftliche Benachrichtigungen: `{{ name }}`, `{{ time_until }}`, `{{ duration }}`, `{{ reason }}`, `{{ title }}`, `{{ next_run }}`.

---

### Datenmodell: Voice-Konfiguration (`voice`)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `enabled` | bool | Sprachkanal aktiv/inaktiv |
| `provider` | string | `alexa_media_player`, `google_cast`, `sonos`, `generic_tts` |
| `media_player_entity` | string | HA-Entitäts-ID des Zielgeräts (z.B. `media_player.echo_dot_kueche`) |
| `media_player_entities` | list[str] | Optional: mehrere Geräte gleichzeitig (Gruppe) |
| `volume` | float | Lautstärke 0.0–1.0 (Standard: 0.5) |
| `restore_volume` | bool | Lautstärke nach Ansage wiederherstellen (Standard: `true`) |
| `tts_engine` | string\|None | TTS-Service (z.B. `tts.cloud_say`, `tts.piper`); bei Alexa: `null` |
| `language` | string\|None | Sprachcode (z.B. `de-DE`, `en-US`); bei Alexa: `null` |
| `announce_mode` | string | Alexa-spezifisch: `announce` (unterbricht kurz) oder `tts` (wartet auf Ende) |

---

### Übersicht: Sprachbenachrichtigungs-Integrationen

| Integration | Gerätetypen | Installation | Benötigt TTS-Engine | Empfehlung |
|-------------|-------------|-------------|---------------------|-----------|
| **Alexa Media Player** | Amazon Echo, Echo Dot, Echo Show, Echo Studio | ⚠️ HACS ([Link](https://github.com/alandtse/alexa_media_player)) | Nein (Alexa intern) | ⭐⭐⭐⭐⭐ Beste Lösung für Alexa-Nutzer |
| **Google Home / Cast** | Google Home, Nest Mini/Hub, Chromecast Audio | ✅ HA Core | Ja (z.B. `tts.cloud_say`) | ⭐⭐⭐⭐⭐ Beste Lösung für Google-Nutzer |
| **Sonos** | Alle Sonos-Lautsprecher | ✅ HA Core | Ja | ⭐⭐⭐⭐ Gut für Sonos-Nutzer |
| **HA TTS + Media Player** | Beliebig (VLC, ESPHome, Kodi…) | ✅ HA Core | Ja | ⭐⭐⭐ Universell |

---

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

### Schritt 2b – Sprachbenachrichtigungen (optional)
- Integration auswählen: "Kein Sprachkanal", "Alexa Media Player", "Google Home / Cast", "Sonos", "HA TTS + Media Player (generisch)"
- **Alexa Media Player**: Auswahl der `media_player.echo_*`-Entität, Lautstärke (0–100 %), Ansagemodus (`announce` / `tts`)
  > ⚠️ Hinweis: Alexa Media Player muss via HACS installiert sein → https://github.com/alandtse/alexa_media_player
- **Google Home / Cast, Sonos, generisch**: Auswahl der `media_player.*`-Entität, TTS-Engine (aus vorhandenen HA-TTS-Services), Sprache, Lautstärke
- Bearbeitung der Standard-Sprachtextvorlagen (Vorab, Nachher, Abschluss, Reminder)
- Test-Ansage: „Test-Ansage abspielen" sendet sofort eine Beispielnachricht auf das gewählte Gerät

### Schritt 3 – Externe Kalender-Accounts (optional, wiederholbar)
- Provider auswählen: Microsoft 365 / Outlook, Google Calendar, Apple iCloud Calendar
- **Microsoft 365**:
  - **Account-Typ auswählen**: „Privat (outlook.com / hotmail.com / live.com)" oder „Business (Microsoft 365 / Azure AD)"
    - Bei Privat-Account: Business-exklusive Features (Teams-Präsenz, Planner, SharePoint) werden in der gesamten UI ausgeblendet
    - Bei Business-Account: Alle Features sichtbar und konfigurierbar
  - **OAuth2-App-Zugangsdaten eingeben**: Client-ID und (optional) Client-Secret aus der eigenen Azure-App-Registrierung eingeben (Anleitung → Abschnitt 16.1)
  - Device Code Flow starten: Code wird angezeigt → Benutzer öffnet `https://microsoft.com/devicelogin` und gibt Code ein → Token wird gespeichert
- **Google**:
  - **OAuth2-App-Zugangsdaten eingeben**: Client-ID und Client-Secret aus dem eigenen Google Cloud-Projekt eingeben (Anleitung → Abschnitt 16.2)
  - OAuth2 Authorization Code Flow mit PKCE → Redirect auf lokalen HA-Callback → Token wird gespeichert
  - ⚠️ Hinweis: Nicht verifizierte Google-Apps zeigen beim Login eine Sicherheitswarnung – dies ist bei eigenen App-Registrierungen normal
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
| **Token-Sicherheit** | AES-256-Verschlüsselung via HA `secrets` / `keyring`, kein Klartext in Storage |
| **Konfliktlösung bei Sync** | Konfigurierbar pro Account: `ha_wins`, `remote_wins`, `newest_wins`, `manual` |
| **OAuth2-App-Registrierung** | Eigene App-Registrierung durch den Nutzer (keine zentrale App; zentrale Registrierung ggf. in späterer Phase) |
| **Microsoft-Account-Typ im Setup** | Im Config Flow explizit zwischen „Privat (outlook.com / hotmail.com)" und „Business (M365 / Azure AD)" unterscheiden; Business-exklusive Features werden für Privat-Accounts ausgeblendet |
| **Business-only-Features in der UI** | Features wie Teams-Präsenz und Planner werden vollständig ausgeblendet, wenn ein privater Microsoft-Account erkannt wurde |
| **OAuth-Setup-Anleitungen** | Schritt-für-Schritt-Anleitungen für Microsoft Azure App Registration und Google Cloud OAuth (Stand 2026) in Abschnitt 16 aufgenommen |
| **Mehrfach-Benachrichtigungskanäle** | Mehrere Kanäle pro Timer/Termin gleichzeitig wählbar; UI: Multi-Select-Feld (Checkboxen) |
| **Bedingungslogik AND/OR-Gruppen** | Verschachtelte Gruppen `(A AND B) OR C` werden unterstützt (Baumstruktur, beliebige Tiefe); UI zeigt eingerückte Gruppe mit AND/OR-Selektor |
| **YAML-Experten-Modus** | Live-Editor mit Syntax-Highlighting (CodeMirror); editierter YAML kann direkt als Timer-Konfiguration übernommen werden |

### Empfohlene Designentscheidungen

- **Storage statt SQLite**: HA Storage API ist die idiomatische Lösung, kein eigenes Datenbankschema
- **DataUpdateCoordinator**: Zentrales State-Management, alle Plattformen subscriben darauf
- **asyncio nativ**: Keine blocking calls, alles async
- **HACS von Anfang an**: Ermöglicht einfache Distribution und Updates für Laien
- **config_entries**: Multi-Instance-Support über HA-Standard-Mechanismus

> ℹ️ Alle offenen Fragen aus der Konzeptphase sind beantwortet und in die Entscheidungstabelle oben sowie in die jeweiligen Abschnitte eingearbeitet.

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

### 11.8 Experten-Modus: YAML-Code-Ansicht & Export

Für Nutzer mit fortgeschrittenen HA-Kenntnissen soll es möglich sein, die **vollständige, von der Integration generierte HA-Automatisierungs-YAML** (inkl. Bedingungen, Aktionen und Benachrichtigungen) einzusehen, zu bearbeiten und zu exportieren.

**Funktionen:**
- **Live-Editor mit Syntax-Highlighting**: Ein eingebetteter **CodeMirror**-Editor zeigt den generierten HA-Automatisierungs-YAML direkt im Browser an – mit YAML-Syntax-Highlighting, Zeilennummern und Fehlermarkierungen. Der Editor ist für Anfänger didaktisch wertvoll: Er macht sichtbar, wie UI-Konfigurationen als YAML-Automatisierungen aussehen.
- **Direkte Übernahme**: Änderungen im Editor können per Klick auf „Übernehmen" direkt als Timer-Konfiguration gespeichert werden. Der YAML wird dabei validiert und in das interne ATC-Datenmodell zurückkonvertiert.
- **Export**: Download des YAML-Codes als `.yaml`-Datei oder Kopieren in die Zwischenablage für die Verwendung in eigenen `automations.yaml`-Dateien.
- **Import**: Benutzer können einen eigenen HA-Automatisierungs-YAML einfügen oder hochladen, der dann als ATC-Timer/Termin importiert wird (soweit das Schema kompatibel ist).
- **Fehlerbehandlung**: Bei ungültigem YAML oder inkompatiblem Schema wird eine verständliche Fehlermeldung angezeigt; die bestehende Konfiguration bleibt erhalten.

**Beispiel-YAML (generiert):**
```yaml
alias: "ATC: Bewässerung Garten"
description: "Generiert von ATC – Timer ID: abc-123"
trigger:
  - platform: time
    at: "06:00:00"
condition:
  - condition: numeric_state
    entity_id: sensor.outdoor_temperature
    above: 10
    below: 30
action:
  - service: switch.turn_on
    target:
      entity_id: switch.valve_zone_1
  - delay:
      minutes: 10
  - service: switch.turn_off
    target:
      entity_id: switch.valve_zone_1
  - service: notify.mobile_app_iphone
    data:
      message: "✅ Bewässerung Zone 1 abgeschlossen."
mode: single
```

**UI-Integration**: Erreichbar über eine Schaltfläche „YAML-Editor öffnen" in der Timer-Detailansicht des ATC-Dashboards sowie in der `atc-timer-card`. Der Editor öffnet sich als modaler Dialog mit dem CodeMirror-Live-Editor.

---

## 12. Phasenplan (Umsetzungsempfehlung)

### Phase 1 – Kern (MVP)
- HACS-Konformität (`hacs.json`, HACS-konforme Struktur)
- Persistenz & Storage (inkl. Migrations-Engine)
- Multi-Instance-Support via `config_entries`
- Scheduler-Engine (`daily`, `weekdays`, `interval`, `yearly`, `once`)
- Aktionen (`turn_on`, `turn_off`, Dauer pro Aktion/Entität)
- Bedingungen (Entitätszustand, numerisch kleiner/größer, numerischer Bereich von/bis, Template, AND/OR, Haltezeit)
- HA-Entitäten (Switch, Sensor)
- Config Flow (ohne Telegram, ohne externe Kalender)
- Kalender-Plattform
- Services
- **Lovelace Custom Cards** (`atc-timer-card`, `atc-reminder-card`, `atc-status-card`)
- **ATC-Dashboard** (automatisch installiertes Standard-Dashboard)

### Phase 2 – Benachrichtigungen, Telegram & Reminder
- Telegram Modus A (eigenständig, nur Outbound)
- Telegram Modus B (HA-Integration, bidirektional & interaktiv via Inline-Keyboards)
- **HA Notify** als Benachrichtigungskanal (zusätzlich zu Telegram, kombinierbar)
- **Sprachbenachrichtigungen** (Voice Notifications):
  - Alexa Media Player (HACS, https://github.com/alandtse/alexa_media_player)
  - Google Home / Google Cast (nativ)
  - Sonos (nativ)
  - HA TTS + generischer Media Player
  - Vordefinierte & konfigurierbare Sprachtextvorlagen (TTS-optimiert, ohne Emojis)
  - Lautstärke-Steuerung, Geräteauswahl, Gruppen-Ansagen
- **Strukturierte Benachrichtigungszeitpunkte** (Vorab, Nachher, Abschluss/Reset) mit Zeiteinheiten Minuten/Stunden/Tage/Wochen
- **Anpassbare Benachrichtigungstexte** mit vorgeschlagenen Standard-Vorlagen (pro Timer/Termin)
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
- Import/Export (YAML/JSON Backup & Teilen)
- **Experten-Modus: YAML-Code-Ansicht, Bearbeitung & Export** (vollständige Automatisierungs-YAML pro Timer/Termin)
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

> **Hinweis zu Account-Typen**: Diese Integration ist primär für **private Accounts** ausgelegt. Features, die ausschließlich mit Microsoft 365 Business/Work-Accounts (Azure AD) oder Google Workspace verfügbar sind, werden im gesamten Abschnitt 14 und 15 mit 🏢 markiert. Funktionen, die für beide Account-Typen verfügbar sind, tragen das Zeichen ✅. Funktionen, die zusätzliche Einrichtung erfordern, sind mit ⚠️ gekennzeichnet.

| Provider | Protokoll / API | Authentifizierung | Account-Typen |
|----------|----------------|-------------------|---------------|
| Microsoft 365 / Outlook | Microsoft Graph API (REST) | OAuth2 – Device Code Flow oder Authorization Code Flow mit PKCE | ✅ Privat (outlook.com) & 🏢 Business (M365) |
| Google Calendar | Google Calendar API v3 (REST) | OAuth2 – Authorization Code Flow mit PKCE | ✅ Privat (gmail.com) & 🏢 Business (Workspace) |
| Apple iCloud Calendar | CalDAV (RFC 4791) | App-spezifisches Passwort (Apple-ID + iCloud Passwort-Alternative) | ✅ Privat & Business |
| Exchange Server (On-Premise) | EWS (Exchange Web Services) oder CalDAV | NTLM / Basic Auth / Modern Auth | 🏢 Nur Business |

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
3. Account-Typ auswählen:
   ○ Privat (outlook.com / hotmail.com / live.com)
   ○ Business (Microsoft 365 / Azure AD / Entra ID)
   → Business-exklusive Features (Teams-Präsenz, Planner, SharePoint) werden
     nur bei Account-Typ „Business" in der UI angezeigt.
4. Azure App-Registrierung eingeben:
   Client-ID:     [________________________________]
   Client-Secret: [________________________________] (optional für Device Code Flow)
   → Anleitung zur App-Registrierung: Abschnitt 16.1
5. Device Code Flow starten:
   → Code wird angezeigt: „Gehe zu https://microsoft.com/devicelogin und gib ein: ABCD-EFGH"
   → Integration wartet auf Authentifizierung (Timeout: 5 Minuten)
   → Nach Erfolg: „✅ Erfolgreich authentifiziert als max@contoso.com"
6. Kalender-Liste wird geladen → Benutzer wählt Kalender aus
7. Pro Kalender: Sync-Richtung (Bidirektional / Nur eingehend / Nur ausgehend)

ℹ️ Privatnutzer (outlook.com) müssen eine eigene Azure-App registrieren.
   Vollständige Schritt-für-Schritt-Anleitung → Abschnitt 16.1

── Google Calendar ────────────────────────────────────────────
2. Anzeigename eingeben
3. Google Cloud OAuth-Zugangsdaten eingeben:
   Client-ID:     [________________________________]
   Client-Secret: [________________________________]
   → Anleitung zur Google Cloud OAuth-Einrichtung: Abschnitt 16.2
4. OAuth2 Authorization URL wird generiert:
   → HA öffnet HA-internen Callback-Endpoint auf Port 8123
   → Benutzer öffnet URL im Browser → meldet sich bei Google an → erteilt Berechtigung
   → Nach Redirect: Token automatisch gespeichert
   ⚠️ Hinweis: Nicht verifizierte Apps zeigen beim Login eine Google-Sicherheitswarnung –
      dies ist bei eigenen Client-IDs normal und kann weggeklickt werden.
5. Kalender-Liste → Auswahl → Sync-Richtung

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

### 14.10 Account-Typ-Kompatibilität

Die folgende Tabelle gibt eine Übersicht, welche Funktionen mit welchem Account-Typ verfügbar sind. **Private Accounts** (outlook.com, gmail.com, apple.com) sind der primäre Zielbereich dieser Integration.

| Feature | Privat (Outlook.com) | Privat (Gmail) | 🏢 Business (M365) | 🏢 Business (Workspace) |
|---------|----------------------|----------------|--------------------|-------------------------|
| **Kalender-Sync bidirektional** | ✅ | ✅ | ✅ | ✅ |
| **Kalender-Trigger (Keyword)** | ✅ | ✅ | ✅ | ✅ |
| **Graph/Push-Webhooks** | ✅ (max. 3 Tage) | ✅ (max. 7 Tage) | ✅ | ✅ |
| **Microsoft To Do Sync** | ✅ | – | ✅ | – |
| **Google Tasks Sync** | – | ✅ | – | ✅ |
| **Outlook E-Mail-Trigger** | ✅ | – | ✅ | – |
| **Gmail E-Mail-Trigger** | – | ⚠️ (*) | – | ✅ |
| **E-Mail senden (Service)** | ✅ | ⚠️ (*) | ✅ | ✅ |
| **OneDrive Backup** | ✅ (5 GB gratis) | – | ✅ (1 TB+) | – |
| **Teams-Präsenz** | ❌ | – | ✅ | – |
| **Microsoft Planner** | ❌ | – | ✅ | – |
| **SharePoint-Datei-Trigger** | ❌ | – | ✅ | – |
| **Google Meet Präsenz** | – | ✅ (**) | – | ✅ (**) |
| **Apple Kalender (CalDAV)** | ✅ | – | ✅ | – |
| **Apple Reminders (VTODO)** | ⚠️ (***) | – | ⚠️ (***) | – |

(*) Erfordert eigenes Google Cloud-Projekt + Pub/Sub-Einrichtung; für restricted Scopes (Gmail) ggf. App-Verifizierung durch Google notwendig.  
(**) Kein direkter Google Meet API-Endpunkt; Meeting-Status wird indirekt aus Calendar-Ereignissen mit Meet-Link abgeleitet – funktioniert für alle Account-Typen gleich.  
(***) Apple unterstützt VTODO über CalDAV nur eingeschränkt; Funktionalität kann je nach iCloud-Version variieren.

---

## 15. Weitere Microsoft Office / Produktivitäts-Integrationen

### 15.1 Microsoft Teams – Präsenz & Meeting-Steuerung 🏢 *(Nur Microsoft 365 Business/Work-Account)*

> ⚠️ **Account-Einschränkung**: Die Graph Presence API (`/me/presence`) ist ausschließlich für Microsoft 365 Business/Work-Accounts (Azure AD / Entra ID) verfügbar. Private Microsoft-Accounts (outlook.com, hotmail.com, live.com) haben **keinen Zugang** zu dieser API. Microsoft Teams Consumer (Privatversion) unterstützt die Presence API nicht. Diese Funktion ist daher nur für Nutzer mit einem Unternehmenskonto nutzbar.

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

**Microsoft To Do** ✅ *(Privat & Business)*:
- REST API: Aufgabenlisten lesen/schreiben (`/me/todo/lists/{listId}/tasks`)
- Bidirektionaler Sync mit HA ToDo-Plattform
- Fällige Aufgaben als HA-Reminder → Benachrichtigung via Telegram
- Neue Aufgaben aus HA heraus erstellen (via HA Dashboard oder Service)

**Microsoft Planner** (Team-Aufgaben) 🏢 *(Nur Business)*:
- Aufgaben-Status als HA-Sensor (z.B. Projektfortschritt)
- Neue Aufgaben bei bestimmten HA-Events erstellen (z.B. „Filter wechseln" wenn Luftqualitäts-Sensor Grenzwert überschreitet)

> ⚠️ **Account-Einschränkung (Planner)**: Microsoft Planner ist ausschließlich mit Microsoft 365 Business/Work-Accounts (Azure AD) verfügbar und nicht für private Outlook.com-Accounts zugänglich.

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

**OneDrive Personal** ✅ *(Privat & Business)*:

**Szenarien**:
- Automatisches Backup von HA-Konfiguration auf OneDrive (täglich/wöchentlich)
- Export von Timer/Reminder-Daten auf OneDrive
- Datei-Trigger: Neue Datei in OneDrive-Ordner → HA-Aktion (z.B. Bild von Türkamera → automatisch hochladen)

**Technische Umsetzung**:
- Graph API: `/me/drive/root:/Pfad:/children` für Datei-Upload
- Service `atc.backup_to_onedrive`: Manuelles oder automatisches Backup
- Webhook auf OneDrive-Ordner für Datei-Trigger

> ℹ️ **Hinweis**: Private Accounts haben 5 GB kostenlosen OneDrive-Speicher. Für Backups ist dies ausreichend.

**SharePoint** 🏢 *(Nur Business)*:
- SharePoint-Datei-Trigger und Ordner-Webhooks sind ausschließlich mit Microsoft 365 Business/Work-Accounts verfügbar.
- Private Microsoft-Accounts haben keinen Zugang zu SharePoint-Ressourcen.

### 15.5 Google Workspace – Erweiterungen

**Google Tasks** ✅ *(Privat & Business)*:
- Bidirektionaler Sync mit HA ToDo-Plattform (analog Microsoft To Do)
- Aufgaben als HA-Reminder, Erledigung aus HA heraus

**Google Meet – Präsenz** ✅ *(Privat & Business, indirekt via Google Calendar)*:
- Meeting-Status aus laufenden Google Calendar-Ereignissen ableiten
- `binary_sensor.atc_google_in_meeting_<name>` wenn Termin mit Meet-Link aktiv ist

> ℹ️ **Hinweis**: Es gibt keinen direkten Google Meet Presence API-Endpunkt (weder für private noch Business-Accounts). Der Meeting-Status wird ausschließlich aus aktiven Google Calendar-Ereignissen mit Meet-Link abgeleitet – dies funktioniert für alle Account-Typen gleich und ist keine Einschränkung gegenüber Business-Accounts.

**Google Gmail – E-Mail-Trigger** ⚠️ *(Eingeschränkt für Privatnutzer)*:
- Gmail API (Pub/Sub Push) für E-Mail-Trigger
- Service `atc.send_gmail`: E-Mail senden via Gmail API

> ⚠️ **Hinweis für Privatnutzer**: Die Gmail API erfordert ein Google Cloud-Projekt mit aktiviertem Pub/Sub. Gmail-Scopes gelten bei Google als „restricted" und erfordern für eine zentrale App-Registrierung eine aufwändige App-Verifizierung durch Google (Security Assessment, Datenschutzerklärung, Domain-Bestätigung). Für Privatnutzer mit eigener Client-ID ist die Nutzung möglich, zeigt aber eine Google-Sicherheitswarnung beim Login (→ Offene Frage 15).

### 15.6 Apple-Erweiterungen

**Apple Reminders (via CalDAV-Erweiterung)**:
- Teilweise über CalDAV VTODO-Komponenten zugänglich
- Sync mit HA ToDo-Plattform

**iCloud Drive**:
- Kein offizielles API – über Drittanbieter-Bibliotheken eingeschränkt möglich; nicht empfohlen für produktiven Einsatz

### 15.7 Übersichts-Tabelle: Integrations-Roadmap

| Feature | Provider | Priorität | Komplexität | Phase | Account-Typ |
|---------|----------|-----------|-------------|-------|-------------|
| Kalender-Sync bidirektional | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | Hoch | 3 | ✅ Alle |
| Kalender-Trigger (Keyword) | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | Mittel | 3 | ✅ Alle |
| Teams-Präsenz-Sensor | Microsoft | ⭐⭐⭐⭐ | Mittel | 4 | 🏢 Nur Business |
| To Do Sync | Microsoft | ⭐⭐⭐⭐ | Mittel | 4 | ✅ Privat & Business |
| Tasks Sync | Google | ⭐⭐⭐⭐ | Mittel | 4 | ✅ Privat & Business |
| E-Mail-Trigger (Inbox) | Microsoft / Google | ⭐⭐⭐ | Mittel | 4 | ✅ / ⚠️ (*) |
| E-Mail senden (Service) | Microsoft / Google | ⭐⭐⭐ | Niedrig | 4 | ✅ / ⚠️ (*) |
| OneDrive Backup | Microsoft | ⭐⭐⭐ | Niedrig | 4 | ✅ Privat (5 GB) & Business |
| Planner-Aufgaben | Microsoft | ⭐⭐ | Mittel | 5 | 🏢 Nur Business |
| SharePoint-Datei-Trigger | Microsoft | ⭐⭐ | Hoch | 5 | 🏢 Nur Business |
| iCloud Drive | Apple | ⭐ | Sehr hoch | – | – (kein offizielles API) |

(*) Microsoft Outlook: ✅ Privat & Business. Google Gmail: ⚠️ Erfordert Google Cloud-Projekt + Pub/Sub; für zentrale App ggf. App-Verifizierung durch Google notwendig.

---

## 16. OAuth2-Einrichtungsanleitungen (Stand 2026)

> Diese Anleitungen beschreiben den aktuellen Stand der Plattformen (Stand: 2026). Da sich Portale ändern können, wird empfohlen, die offizielle Microsoft- bzw. Google-Dokumentation als Ergänzung zu nutzen.

---

### 16.1 Microsoft Azure App-Registrierung (für Outlook / Microsoft 365)

**Voraussetzung**: Ein Microsoft-Konto (privat: outlook.com / hotmail.com, oder Business: Microsoft 365-Konto mit Admin-Rechten für App-Registrierungen). Privatnutzer mit outlook.com können eine kostenlose App im Azure-Portal registrieren – ein bezahltes Azure-Abonnement ist **nicht** erforderlich.

#### Schritt-für-Schritt-Anleitung

**1. Azure Portal öffnen**
- Rufe [https://portal.azure.com](https://portal.azure.com) auf und melde dich mit deinem Microsoft-Konto an.
- Wenn du ein privates Outlook-/Hotmail-Konto verwendest: Melde dich direkt mit diesem an. Das Azure-Portal ist für alle Microsoft-Konten zugänglich (kein Abonnement nötig für kostenlose Registrierungen).

**2. Microsoft Entra ID öffnen**
- Suche im oberen Suchfeld nach **„Microsoft Entra ID"** (früher: Azure Active Directory) und öffne den Dienst.

**3. App-Registrierungen**
- Klicke im linken Menü auf **„App-Registrierungen"**.
- Klicke oben auf **„+ Neue Registrierung"**.

**4. App konfigurieren**
- **Name**: z.B. `HA Advanced Timer & Calendar`
- **Unterstützte Kontotypen**: Wähle entsprechend deinem Account-Typ:
  - Für **Privatnutzer** (outlook.com): **„Persönliche Microsoft-Konten (z.B. Xbox und Skype)"** → wähle die Option „Konten in einem Organisationsverzeichnis (beliebig) und persönliche Microsoft-Konten"
  - Für **Business-Nutzer** (Microsoft 365 / Azure AD): „Nur Konten in diesem Organisationsverzeichnis" oder die Multi-Tenant-Option
- **Umleitungs-URI**: Wähle **„Mobile und Desktopanwendungen"** und gib ein: `http://localhost` (für Device Code Flow wird kein Redirect benötigt, aber dieser Wert ist ein sicherer Platzhalter)
- Klicke auf **„Registrieren"**.

**5. Client-ID kopieren**
- Nach der Registrierung erscheint die **Übersichtsseite** der App.
- Kopiere die **„Anwendungs-ID (Client)"** – das ist deine **Client-ID** für ATC.

**6. API-Berechtigungen hinzufügen**
- Klicke im linken Menü auf **„API-Berechtigungen"** → **„+ Berechtigung hinzufügen"**.
- Wähle **„Microsoft Graph"** → **„Delegierte Berechtigungen"**.
- Füge folgende Berechtigungen hinzu:
  - `Calendars.ReadWrite` – Kalender lesen und schreiben
  - `offline_access` – Refresh Token (für dauerhaften Zugriff ohne erneutes Login)
  - `User.Read` – Benutzerprofil lesen (für Anzeigename)
  - *(Optional für Business)* `Presence.Read` – Teams-Präsenz lesen
  - *(Optional für Business)* `Tasks.ReadWrite` – Microsoft To Do / Planner
  - *(Optional)* `Mail.Read`, `Mail.Send` – E-Mail-Trigger und -Versand
- Klicke auf **„Berechtigungen hinzufügen"**.
- **Für Privatnutzer**: Administrator-Zustimmung ist **nicht** erforderlich – die delegierten Berechtigungen werden beim ersten Login durch den Nutzer erteilt.

**7. Authentication-Einstellungen (für Device Code Flow)**
- Klicke im linken Menü auf **„Authentifizierung"**.
- Scrolle zu **„Erweiterte Einstellungen"** und aktiviere **„Öffentliche Clientflows zulassen"** → Stelle den Toggle auf **„Ja"**.
- Klicke auf **„Speichern"**.

**8. Kein Client-Secret erforderlich (Device Code Flow)**
- Für den Device Code Flow (empfohlen für ATC) wird **kein** Client-Secret benötigt.
- Falls du den Authorization Code Flow verwenden möchtest: Klicke auf **„Zertifikate und Geheimnisse"** → **„+ Neuer geheimer Clientschlüssel"** → kopiere den generierten Wert sofort (er wird nur einmal angezeigt).

**9. Zugangsdaten in ATC eintragen**
- **Client-ID**: Die kopierte Anwendungs-ID aus Schritt 5
- **Client-Secret**: Nur bei Authorization Code Flow; bei Device Code Flow leer lassen
- Starte den Device Code Flow in ATC → öffne `https://microsoft.com/devicelogin` und gib den angezeigten Code ein.

> ℹ️ **Hinweis für Privatnutzer**: Wenn beim ersten Login die Meldung erscheint, dass eine Admin-Zustimmung benötigt wird, dann wurde möglicherweise eine falsche „Unterstützte Kontotypen"-Option gewählt. Stelle sicher, dass persönliche Microsoft-Konten in der App-Registrierung aktiviert sind.

---

### 16.2 Google Cloud OAuth-Einrichtung (für Google Calendar / Gmail)

**Voraussetzung**: Ein Google-Konto (privat: gmail.com, oder Workspace). Ein kostenloses Google-Konto genügt für die Erstellung eines Google Cloud-Projekts.

#### Schritt-für-Schritt-Anleitung

**1. Google Cloud Console öffnen**
- Rufe [https://console.cloud.google.com](https://console.cloud.google.com) auf und melde dich mit deinem Google-Konto an.

**2. Neues Projekt erstellen**
- Klicke oben links auf das Projekt-Dropdown (oder **„Projekt auswählen"**).
- Klicke auf **„Neues Projekt"**.
- **Projektname**: z.B. `HA Advanced Timer Calendar`
- Klicke auf **„Erstellen"**.
- Warte bis das Projekt erstellt ist und wähle es aus.

**3. Google Calendar API aktivieren**
- Öffne im linken Menü **„APIs und Dienste"** → **„Bibliothek"**.
- Suche nach **„Google Calendar API"** und klicke darauf.
- Klicke auf **„Aktivieren"**.
- *(Optional, für Gmail-E-Mail-Trigger)* Suche und aktiviere auch die **„Gmail API"**.

**4. OAuth-Zustimmungsbildschirm konfigurieren**
- Öffne **„APIs und Dienste"** → **„OAuth-Zustimmungsbildschirm"**.
- Wähle **„Extern"** (für persönliche Google-Konten; „Intern" ist nur für Google Workspace-Organisationen).
- Klicke auf **„Erstellen"**.
- **App-Name**: z.B. `HA Advanced Timer Calendar`
- **Nutzersupport-E-Mail**: Deine Gmail-Adresse
- **Entwicklerkontakt-E-Mail**: Deine Gmail-Adresse
- Klicke auf **„Speichern und weiter"**.

**5. Scopes konfigurieren**
- Klicke auf **„Bereiche hinzufügen oder entfernen"**.
- Füge folgende Scopes hinzu:
  - `https://www.googleapis.com/auth/calendar` – Kalender lesen und schreiben
  - `https://www.googleapis.com/auth/calendar.events` – Ereignisse lesen und schreiben
  - *(Optional, für Gmail)* `https://www.googleapis.com/auth/gmail.readonly`
- Klicke auf **„Aktualisieren"** und dann **„Speichern und weiter"**.

**6. Test-Nutzer hinzufügen (wichtig für externe, nicht verifizierte Apps)**
- Klicke auf **„+ Nutzer hinzufügen"**.
- Gib deine eigene Gmail-Adresse ein.
- *(Optional)* Füge weitere Adressen hinzu, die die App nutzen sollen.
- Klicke auf **„Speichern und weiter"**.

> ⚠️ **Hinweis**: Da die App nicht durch Google verifiziert ist, erscheint beim Login eine Sicherheitswarnung: „Diese App wurde von Google nicht verifiziert". Dies ist bei eigenen OAuth-Apps für den Privatgebrauch normal. Klicke auf **„Erweitert"** → **„Weiter zu [App-Name] (unsicher)"**, um fortzufahren. Als Test-Nutzer (Schritt 6) kannst du die App ohne Einschränkungen nutzen.

**7. OAuth-Client-ID erstellen**
- Öffne **„APIs und Dienste"** → **„Anmeldedaten"**.
- Klicke auf **„+ Anmeldedaten erstellen"** → **„OAuth-Client-ID"**.
- **Anwendungstyp**: **„Webanwendung"**
- **Name**: z.B. `HA ATC Client`
- **Autorisierte Weiterleitungs-URIs**: Füge hinzu:
  - `http://localhost:8123/auth/external/callback` (für HA lokalen Zugriff)
  - `https://<deine-ha-domain>/auth/external/callback` (falls du HA über eine externe Domain erreichst)
- Klicke auf **„Erstellen"**.

**8. Client-ID und Client-Secret kopieren**
- Ein Dialogfeld zeigt **Client-ID** und **Clientschlüssel (Client-Secret)** an.
- Kopiere beide Werte sofort – das Secret wird nur einmal vollständig angezeigt (es kann aber jederzeit neu generiert werden).

**9. Zugangsdaten in ATC eintragen**
- **Client-ID**: Die kopierte Client-ID aus Schritt 8
- **Client-Secret**: Der kopierte Clientschlüssel aus Schritt 8
- Starte den OAuth-Flow in ATC → ein Browser-Fenster öffnet sich für den Google-Login.

> ℹ️ **Hinweis zur App-Verifizierung**: Für den Privatgebrauch (eigene Client-ID, eigene Test-Nutzer) ist keine Verifizierung durch Google erforderlich. Eine Google-Verifizierung wäre nur nötig, wenn die App öffentlich für andere Nutzer bereitgestellt werden soll (→ zentrale App-Registrierung in einer späteren Phase).

---
