# HA Advanced Timer & Calendar – Benutzerhandbuch

## Inhaltsverzeichnis

1. [Einführung & Funktionsübersicht](#1-einführung--funktionsübersicht)
2. [Installation über HACS](#2-installation-über-hacs)
3. [Ersteinrichtung (Config Flow)](#3-ersteinrichtung-config-flow)
4. [Timer erstellen](#4-timer-erstellen)
5. [Erinnerungen & Aufgaben erstellen](#5-erinnerungen--aufgaben-erstellen)
6. [Bedingungen (Conditions)](#6-bedingungen-conditions)
7. [Benachrichtigungen einrichten](#7-benachrichtigungen-einrichten)
8. [Dashboard & Lovelace-Karten](#8-dashboard--lovelace-karten)
9. [Externe Kalender-Integration](#9-externe-kalender-integration)
10. [HA-Services-Referenz](#10-ha-services-referenz)
11. [FAQ & Fehlerbehebung](#11-faq--fehlerbehebung)

---

## 1. Einführung & Funktionsübersicht

**HA Advanced Timer & Calendar** (ATC) ist eine leistungsstarke benutzerdefinierte Komponente für Home Assistant, die flexibles Zeitplanen, Erinnerungen und externe Kalendersynchronisation in einer einzigen Integration vereint.

### Kernfunktionen

| Funktion | Beschreibung |
|---|---|
| **Flexible Timer** | Täglich, Wochentage, Intervall, Cron, Sonnenaufgang/Untergang, jährlich |
| **Erinnerungen & To-Dos** | Einmalige und wiederkehrende Erinnerungen, Jahrestage, Termine |
| **Bedingungen** | UND/ODER-Bedingungsgruppen auf Entity-Status, numerische Werte, Templates |
| **Intelligente Bewässerung** | Adaptive Bewässerungsdauer basierend auf Temperatur, Bodenfeuchte, Wetter |
| **Timer-Vorlagen** | Fertige Vorlagen für Bewässerung, Licht, Klima, Sicherheit |
| **Import / Export** | Sicherung und Wiederherstellung aller Timer und Erinnerungen als JSON |
| **Statistiken** | Ausführungsverlauf und Übersprungsrate pro Timer |
| **Benachrichtigungen** | Telegram (Modus A & B), Sprache (Alexa, Google Cast, Sonos, TTS) |
| **Benachrichtigungs-Eskalation** | Erinnerungen wiederholen bis zur Bestätigung |
| **Externe Kalender** | Microsoft 365, Google Calendar, Apple iCloud-Synchronisation |
| **YAML-Export** | Äquivalente HA-Automations-YAML für jeden Timer generieren |

---

## 2. Installation über HACS

### Voraussetzungen

- Home Assistant 2024.1 oder neuer
- [HACS](https://hacs.xyz) installiert

### Schritte

1. **HACS** in der Home Assistant-Seitenleiste öffnen.
2. Auf **Integrationen** klicken → **⋮ (Menü)** → **Benutzerdefinierte Repositories**.
3. Repository-URL eingeben:
   ```
   https://github.com/your-org/HA-Advanced-Timer-and-Calendar
   ```
   Kategorie **Integration** auswählen und auf **Hinzufügen** klicken.
4. Nach **Advanced Timer & Calendar** in HACS suchen und auf **Herunterladen** klicken.
5. Home Assistant neu starten (*Einstellungen → System → Neustart*).
6. Mit der [Ersteinrichtung](#3-ersteinrichtung-config-flow) fortfahren.

---

## 3. Ersteinrichtung (Config Flow)

1. Zu **Einstellungen → Geräte & Dienste → Integration hinzufügen** navigieren.
2. Nach **Advanced Timer & Calendar** suchen und auswählen.
3. Den Einrichtungsassistenten ausfüllen:

   | Feld | Beschreibung | Standard |
   |---|---|---|
   | **Name** | Anzeigename dieser Instanz | `ATC` |
   | **Standard-Erinnerungszeit** | Minuten vor Fälligkeit für Benachrichtigung | `30` |
   | **Telegram-Modus** | `none`, `mode_a` (HA notify), `mode_b` (direkter Bot) | `none` |
   | **Sprachanbieter** | `none`, `alexa_media_player`, `google_cast`, `sonos`, `generic_tts` | `none` |

4. Auf **Bestätigen** klicken. Die Integration erstellt automatisch ihre Entities.

### Erstellte Entities

- `switch.atc_<name>_<timer_name>` – Timer aktivieren/deaktivieren
- `sensor.atc_<name>_next_run` – Nächster geplanter Ausführungszeitpunkt
- `calendar.atc_<name>` – Kalender-Entity für Erinnerungen und Termine
- `todo.atc_<name>` – Aufgabenlisten-Entity

---

## 4. Timer erstellen

Timer werden über das **HA-Services-Panel** (*Entwicklerwerkzeuge → Dienste*) oder in Automatisierungen verwaltet.

### 4.1 Täglicher Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Morgen Gartenbeleuchtung"
  schedule_type: daily
  time: "07:00:00"
  enabled: true
  actions:
    - entity_id: light.garden
      service: light.turn_on
      duration_seconds: 3600
```

### 4.2 Wochentage-Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Wochentagsheizung"
  schedule_type: weekdays
  weekdays: [0, 1, 2, 3, 4]   # 0=Montag … 6=Sonntag
  time: "06:30:00"
  actions:
    - entity_id: climate.living_room
      service: climate.set_temperature
      service_data:
        temperature: 21
```

### 4.3 Intervall-Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Wöchentliches Backup"
  schedule_type: interval
  interval_value: 1
  interval_unit: weeks
  time: "02:00:00"
  actions:
    - entity_id: script.run_backup
      service: script.turn_on
```

### 4.4 Sonnenaufgang / Sonnenuntergang-Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Außenbeleuchtung bei Sonnenuntergang"
  schedule_type: sun
  sun_event: sunset
  sun_offset_minutes: -10      # 10 Minuten vor Sonnenuntergang
  actions:
    - entity_id: light.outdoor
      service: light.turn_on
```

### 4.5 Cron-Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Alle 30 Minuten Sensordaten"
  schedule_type: cron
  cron_expression: "*/30 * * * *"
  actions:
    - entity_id: script.push_sensor_data
      service: script.turn_on
```

### 4.6 Vorlagen verwenden

```yaml
service: advanced_timer_calendar.create_timer
data:
  template_id: irrigation_daily
  name: "Vorgarten"
  overrides:
    time: "05:30:00"
    actions:
      - entity_id: switch.front_valve
        service: switch.turn_on
        duration_seconds: 900
```

Verfügbare Vorlagen: `irrigation_daily`, `irrigation_zones`, `light_morning`, `light_sunset`, `thermostat_weekday`, `vacation_mode`.

### 4.7 Intelligente Bewässerung

Ein Smart-Watering-Profil an einen Bewässerungs-Timer anhängen:

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Intelligente Gartenbewässerung"
  schedule_type: daily
  time: "06:00:00"
  smart_watering:
    base_duration_seconds: 600
    temperature_sensor: sensor.aussentemperatur
    soil_moisture_sensor: sensor.bodenfeuchte_garten
    weather_entity: weather.home
    temperature_high: 30
    rain_probability_threshold: 0.6
    factor_hot: 1.5
    factor_dry: 1.3
  actions:
    - entity_id: switch.garden_valve
      service: switch.turn_on
```

Der Algorithmus:
- **Überspringt** die Bewässerung wenn Regenwahrscheinlichkeit ≥ Schwellenwert
- **Überspringt** wenn Bodenfeuchte ≥ Zielwert
- **Erhöht** Dauer × `factor_hot` bei Temperatur > `temperature_high`
- **Erhöht** Dauer × `factor_dry` wenn Bodenfeuchte < 50 % des Zielwerts
- **Reduziert** Dauer × `factor_cold` bei Temperatur < `temperature_low`

---

## 5. Erinnerungen & Aufgaben erstellen

### 5.1 Einmalige Erinnerung

```yaml
service: advanced_timer_calendar.create_reminder
data:
  title: "Stromrechnung bezahlen"
  due_date: "2024-12-01"
  due_time: "09:00:00"
  reminder_minutes_before: 60
  notes: "Lastschrift Referenz: 1234"
```

### 5.2 Jahrestag (Jährlich wiederkehrend)

```yaml
service: advanced_timer_calendar.create_reminder
data:
  title: "Hochzeitstag"
  type: anniversary
  due_date: "2000-06-15"          # Jahr wird ignoriert; wiederholt sich jedes Jahr
  reminder_minutes_before: 1440   # 1 Tag vorher
```

### 5.3 Aufgabe als erledigt markieren

```yaml
service: advanced_timer_calendar.complete_todo
data:
  reminder_id: "abc123"
```

---

## 6. Bedingungen (Conditions)

Bedingungen ermöglichen es, Timer und Erinnerungen nur auszulösen, wenn bestimmte Kriterien erfüllt sind. Bedingungen können in UND/ODER-Gruppen verschachtelt werden.

### 6.1 Entity-Status-Bedingung

```yaml
conditions:
  type: item
  condition_type: state
  entity_id: binary_sensor.jemand_zuhause
  value: "on"
```

### 6.2 Numerische Bedingungen

```yaml
conditions:
  type: item
  condition_type: numeric_below
  entity_id: sensor.aussentemperatur
  value: 5        # nur auslösen wenn unter 5 °C
```

Unterstützt: `numeric_below`, `numeric_above`, `numeric_between` (erfordert `min_value` und `max_value`).

### 6.3 Template-Bedingung

```yaml
conditions:
  type: item
  condition_type: template
  template: "{{ states('sensor.stromverbrauch') | float < 2000 }}"
```

### 6.4 UND / ODER Gruppen

```yaml
conditions:
  type: group
  operator: and
  conditions:
    - type: item
      condition_type: state
      entity_id: binary_sensor.gast_modus
      value: "off"
    - type: group
      operator: or
      conditions:
        - type: item
          condition_type: numeric_above
          entity_id: sensor.temperature
          value: 25
        - type: item
          condition_type: state
          entity_id: input_boolean.sommermodus
          value: "on"
```

---

## 7. Benachrichtigungen einrichten

### 7.1 Telegram – Modus A (über HA Notify)

Modus A verwendet den in HA bereits konfigurierten `notify`-Dienst:

1. Die [Telegram-Bot-Integration](https://www.home-assistant.io/integrations/telegram/) in HA einrichten.
2. Im ATC Config Flow **Telegram-Modus: mode_a** auswählen.
3. Den `notify`-Dienstnamen eingeben, z. B. `notify.telegram_benutzer`.

Benachrichtigungs-Vorlagenvariablen: `{{ name }}`, `{{ time_until }}`, `{{ reason }}`.

### 7.2 Telegram – Modus B (Direkter Bot)

Modus B sendet Nachrichten direkt ohne die HA-Telegram-Integration:

1. Einen Telegram-Bot über [@BotFather](https://t.me/botfather) erstellen und den Token kopieren.
2. Die eigene Chat-ID herausfinden (Nachricht an `@userinfobot` senden).
3. Im ATC Config Flow **Telegram-Modus: mode_b** auswählen.
4. **Bot-Token** und **Chat-ID** eingeben.

### 7.3 Sprachbenachrichtigungen

| Anbieter | Hinweise |
|---|---|
| `alexa_media_player` | Erfordert [Alexa Media Player](https://github.com/custom-components/alexa_media_player) |
| `google_cast` | Verwendet `tts`-Dienst + Cast |
| `sonos` | Verwendet Sonos TTS |
| `generic_tts` | Beliebiger HA-TTS-Dienst + Media Player |

Im Config Flow unter **Sprachanbieter** konfigurieren und die Ziel-Media-Player-Entity eingeben.

### 7.4 Benachrichtigungs-Eskalation

Eine Benachrichtigung wiederholen bis zur Bestätigung:

```yaml
service: advanced_timer_calendar.create_reminder
data:
  title: "Medikamente nehmen"
  due_time: "08:00:00"
  escalation:
    enabled: true
    interval_minutes: 15
    max_escalations: 4
```

Bestätigen über:
```yaml
service: advanced_timer_calendar.acknowledge_notification
data:
  item_id: "abc123"
  item_type: reminder
```

---

## 8. Dashboard & Lovelace-Karten

### 8.1 Timer-Übersichtskarte

```yaml
type: entities
title: Meine Timer
entities:
  - entity: switch.atc_main_morgen_gartenbeleuchtung
  - entity: sensor.atc_main_morgen_gartenbeleuchtung_next_run
```

### 8.2 Kalender-Karte

Die eingebaute HA-Kalenderkarte funktioniert mit der ATC-Kalender-Entity:

```yaml
type: calendar
entities:
  - calendar.atc_main
initial_view: dayGridMonth
```

### 8.3 Aufgabenlisten-Karte

```yaml
type: todo-list
entity: todo.atc_main
```

### 8.4 Schaltfläche „Jetzt ausführen"

```yaml
type: button
name: "Bewässerung jetzt starten"
tap_action:
  action: call-service
  service: advanced_timer_calendar.run_now
  service_data:
    timer_id: "TIMER_ID_HIER"
```

---

## 9. Externe Kalender-Integration

### 9.1 Microsoft 365 / Outlook

```yaml
service: advanced_timer_calendar.add_calendar_account
data:
  provider: microsoft
  name: "Arbeitskalender"
  client_id: "azure-app-client-id"
  client_secret: "geheimnis"
  tenant_id: "tenant-id"
  sync_direction: bidirectional
```

### 9.2 Google Calendar

```yaml
service: advanced_timer_calendar.add_calendar_account
data:
  provider: google
  name: "Persönlicher Google"
  client_id: "google-client-id"
  client_secret: "google-geheimnis"
  sync_direction: inbound
```

### 9.3 Apple iCloud

```yaml
service: advanced_timer_calendar.add_calendar_account
data:
  provider: apple
  name: "iCloud"
  username: "apple-id@icloud.com"
  password: "app-spezifisches-passwort"
  sync_direction: inbound
```

### 9.4 Manuelle Synchronisation

```yaml
service: advanced_timer_calendar.sync_calendar
data:
  account_id: "abc123"
```

### 9.5 Konfliktlösung

`conflict_strategy` setzen auf:
- `ha_wins` – Lokale ATC-Daten haben Vorrang
- `remote_wins` – Externer Kalender hat Vorrang
- `newest_wins` – Zuletzt geänderter Eintrag gewinnt
- `manual` – Konflikte werden zur manuellen Auflösung markiert

---

## 10. HA-Services-Referenz

| Service | Beschreibung | Wichtige Parameter |
|---|---|---|
| `create_timer` | Neuen Timer erstellen | `name`, `schedule_type`, `time`, `actions` |
| `update_timer` | Bestehenden Timer ändern | `timer_id`, beliebiges Feld |
| `delete_timer` | Timer löschen | `timer_id` |
| `enable_timer` | Deaktivierten Timer aktivieren | `timer_id` |
| `disable_timer` | Deaktivieren ohne Löschen | `timer_id` |
| `pause_timer` | Ausführung pausieren | `timer_id` |
| `skip_next` | Nächste geplante Ausführung überspringen | `timer_id` |
| `run_now` | Timer sofort ausführen | `timer_id` |
| `create_reminder` | Erinnerung/To-Do erstellen | `title`, `due_date`, `due_time` |
| `complete_todo` | Aufgabe als erledigt markieren | `reminder_id` |
| `sync_calendar` | Externe Kalendersynchronisation auslösen | `account_id` (optional) |
| `add_calendar_account` | Externen Kalender hinzufügen | `provider`, `name`, Zugangsdaten |
| `remove_calendar_account` | Externen Kalender entfernen | `account_id` |
| `create_external_event` | Ereignis im externen Kalender erstellen | `account_id`, `title`, `start`, `end` |
| `delete_external_event` | Ereignis im externen Kalender löschen | `account_id`, `event_id` |
| `create_calendar_trigger` | HA-Event aus Kalendereintrag auslösen | `account_id`, `filter`, `event_name` |
| `delete_calendar_trigger` | Kalender-Trigger entfernen | `trigger_id` |

---

## 11. FAQ & Fehlerbehebung

### Timer wird nicht ausgelöst

1. Prüfen, ob die Switch-Entity **eingeschaltet** ist (`switch.atc_<name>_<timer_name>`).
2. Das `time`-Feld im 24-Stunden-Format `HH:MM:SS` überprüfen.
3. Bedingungen prüfen – eine nicht erfüllte Bedingung überspringt die Ausführung lautlos.
4. Logs überprüfen: *Einstellungen → System → Protokolle*, nach `advanced_timer_calendar` filtern.

### Intelligente Bewässerung überspringt immer

- Sensor-Entity-IDs auf Richtigkeit prüfen; die Sensoren dürfen nicht `unavailable` sein.
- `rain_probability_threshold` prüfen: Die Weather-Entity muss `forecast[0].precipitation_probability` als Wert 0–100 bereitstellen.

### Benachrichtigungen werden nicht empfangen

- **Telegram Modus A**: Sicherstellen, dass der `notify`-Dienstname in HA existiert und manuell testen.
- **Telegram Modus B**: Bot-Token und Chat-ID überprüfen. Sicherstellen, dass der Bot gestartet wurde (*/start* senden).
- **Sprache**: Sicherstellen, dass die Media-Player-Entity verfügbar und nicht stummgeschaltet ist.

### Import/Export

Alle Daten exportieren:
```yaml
service: advanced_timer_calendar.export_all
```
Das Ergebnis wird in der Service-Antwort zurückgegeben. Das JSON kopieren und sicher aufbewahren.

Importieren:
```yaml
service: advanced_timer_calendar.import_json
data:
  json_str: '{"atc_export_version":"1.0","timers":[...]}'
  merge: true
```

### Ausführungsstatistiken abrufen

```yaml
service: advanced_timer_calendar.get_timer_stats
data:
  timer_id: "abc123"
  days: 30
```

Gibt zurück: `total_executions`, `fired`, `skipped`, `errors`, `skip_rate`, `avg_duration_seconds`, `last_fired`.

### Verlauf zurücksetzen / löschen

```yaml
service: advanced_timer_calendar.clear_timer_history
data:
  timer_id: "abc123"   # weglassen um gesamten Verlauf zu löschen
```
