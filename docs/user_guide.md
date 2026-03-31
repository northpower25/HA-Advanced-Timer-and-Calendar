# HA Advanced Timer & Calendar – User Guide

## Table of Contents

1. [Introduction & Features](#1-introduction--features)
2. [Installation via HACS](#2-installation-via-hacs)
3. [Initial Setup (Config Flow)](#3-initial-setup-config-flow)
4. [Creating Timers](#4-creating-timers)
5. [Creating Reminders & To-Dos](#5-creating-reminders--to-dos)
6. [Conditions](#6-conditions)
7. [Notifications Setup](#7-notifications-setup)
8. [Dashboard & Lovelace Cards](#8-dashboard--lovelace-cards)
9. [External Calendar Integration](#9-external-calendar-integration)
10. [HA Services Reference](#10-ha-services-reference)
11. [FAQ & Troubleshooting](#11-faq--troubleshooting)

---

## 1. Introduction & Features

**HA Advanced Timer & Calendar** (ATC) is a powerful Home Assistant custom component that combines sophisticated scheduling, reminders, and external calendar synchronisation in a single integration.

### Core Features

| Feature | Description |
|---|---|
| **Flexible Timers** | Daily, weekday, interval, cron, sunrise/sunset, yearly |
| **Reminders & To-Dos** | One-off reminders with recurrence, anniversaries, appointments |
| **Conditions** | AND/OR condition groups on entity state, numeric values, templates |
| **Smart Watering** | Adaptive irrigation based on temperature, soil moisture, and weather |
| **Timer Templates** | Ready-made presets for irrigation, lighting, climate, security |
| **Import / Export** | Backup and restore all timers and reminders as JSON |
| **Statistics** | Execution history and skip-rate analytics per timer |
| **Notifications** | Telegram (Mode A & B), voice (Alexa, Google Cast, Sonos, TTS) |
| **Notification Escalation** | Repeat reminders until acknowledged |
| **External Calendars** | Microsoft 365, Google Calendar, Apple iCloud sync |
| **YAML Export** | Generate equivalent HA automation YAML for any timer |

---

## 2. Installation via HACS

### Prerequisites

- Home Assistant 2024.1 or newer
- [HACS](https://hacs.xyz) installed

### Steps

1. Open **HACS** in the Home Assistant sidebar.
2. Click **Integrations** → **⋮ (menu)** → **Custom repositories**.
3. Enter the repository URL:
   ```
   https://github.com/your-org/HA-Advanced-Timer-and-Calendar
   ```
   Select category **Integration** and click **Add**.
4. Search for **Advanced Timer & Calendar** in HACS and click **Download**.
5. Restart Home Assistant (*Settings → System → Restart*).
6. Proceed with [Initial Setup](#3-initial-setup-config-flow).

---

## 3. Initial Setup (Config Flow)

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Advanced Timer & Calendar** and click it.
3. Complete the setup wizard:

   | Field | Description | Default |
   |---|---|---|
   | **Name** | Display name for this instance | `ATC` |
   | **Default reminder time** | Minutes before due date to send a notification | `30` |
   | **Telegram mode** | `none`, `mode_a` (HA notify), `mode_b` (direct bot) | `none` |
   | **Voice provider** | `none`, `alexa_media_player`, `google_cast`, `sonos`, `generic_tts` | `none` |

4. Click **Submit**. The integration creates its entities automatically.

### Entities Created

- `switch.atc_<name>_<timer_name>` – enable/disable each timer
- `sensor.atc_<name>_next_run` – next scheduled run timestamp
- `calendar.atc_<name>` – calendar entity for reminders and appointments
- `todo.atc_<name>` – to-do list entity

---

## 4. Creating Timers

Timers are managed via the **HA Services** panel (*Developer Tools → Services*) or through automations.

### 4.1 Daily Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Morning Garden Lights"
  schedule_type: daily
  time: "07:00:00"
  enabled: true
  actions:
    - entity_id: light.garden
      service: light.turn_on
      duration_seconds: 3600
```

### 4.2 Weekday Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Weekday Heating"
  schedule_type: weekdays
  weekdays: [0, 1, 2, 3, 4]   # 0=Monday … 6=Sunday
  time: "06:30:00"
  actions:
    - entity_id: climate.living_room
      service: climate.set_temperature
      service_data:
        temperature: 21
```

### 4.3 Interval Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Weekly Backup"
  schedule_type: interval
  interval_value: 1
  interval_unit: weeks
  time: "02:00:00"
  actions:
    - entity_id: script.run_backup
      service: script.turn_on
```

### 4.4 Sunrise / Sunset Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Outdoor Lights Sunset"
  schedule_type: sun
  sun_event: sunset
  sun_offset_minutes: -10      # 10 minutes before sunset
  actions:
    - entity_id: light.outdoor
      service: light.turn_on
```

### 4.5 Cron Timer

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Every 30 min sensor push"
  schedule_type: cron
  cron_expression: "*/30 * * * *"
  actions:
    - entity_id: script.push_sensor_data
      service: script.turn_on
```

### 4.6 Using Templates

```yaml
service: advanced_timer_calendar.create_timer
data:
  template_id: irrigation_daily
  name: "Front Garden"
  overrides:
    time: "05:30:00"
    actions:
      - entity_id: switch.front_valve
        service: switch.turn_on
        duration_seconds: 900
```

Available built-in templates: `irrigation_daily`, `irrigation_zones`, `light_morning`, `light_sunset`, `thermostat_weekday`, `vacation_mode`.

### 4.7 Smart Watering

Attach a smart watering profile to any irrigation timer:

```yaml
service: advanced_timer_calendar.create_timer
data:
  name: "Smart Garden Watering"
  schedule_type: daily
  time: "06:00:00"
  smart_watering:
    base_duration_seconds: 600
    temperature_sensor: sensor.outdoor_temperature
    soil_moisture_sensor: sensor.soil_moisture_garden
    weather_entity: weather.home
    temperature_high: 30
    rain_probability_threshold: 0.6
    factor_hot: 1.5
    factor_dry: 1.3
  actions:
    - entity_id: switch.garden_valve
      service: switch.turn_on
```

The algorithm will:
- **Skip** watering if rain probability ≥ threshold
- **Skip** if soil moisture ≥ target
- **Increase** duration × `factor_hot` when temp > `temperature_high`
- **Increase** duration × `factor_dry` when soil moisture < 50 % of target
- **Decrease** duration × `factor_cold` when temp < `temperature_low`

---

## 5. Creating Reminders & To-Dos

### 5.1 One-Off Reminder

```yaml
service: advanced_timer_calendar.create_reminder
data:
  title: "Pay electricity bill"
  due_date: "2024-12-01"
  due_time: "09:00:00"
  reminder_minutes_before: 60
  notes: "Direct debit reference: 1234"
```

### 5.2 Anniversary (Yearly)

```yaml
service: advanced_timer_calendar.create_reminder
data:
  title: "Wedding Anniversary"
  type: anniversary
  due_date: "2000-06-15"     # year is ignored; recurs every year
  reminder_minutes_before: 1440    # 1 day before
```

### 5.3 Completing a To-Do

```yaml
service: advanced_timer_calendar.complete_todo
data:
  reminder_id: "abc123"
```

---

## 6. Conditions

Conditions allow timers and reminders to fire only when certain criteria are met. Conditions can be nested in AND/OR groups.

### 6.1 Entity State Condition

```yaml
conditions:
  type: item
  condition_type: state
  entity_id: binary_sensor.someone_home
  value: "on"
```

### 6.2 Numeric Conditions

```yaml
conditions:
  type: item
  condition_type: numeric_below
  entity_id: sensor.outdoor_temperature
  value: 5        # only fire if below 5 °C
```

Supported: `numeric_below`, `numeric_above`, `numeric_between` (requires `min_value` and `max_value`).

### 6.3 Template Condition

```yaml
conditions:
  type: item
  condition_type: template
  template: "{{ states('sensor.power_usage') | float < 2000 }}"
```

### 6.4 AND / OR Groups

```yaml
conditions:
  type: group
  operator: and
  conditions:
    - type: item
      condition_type: state
      entity_id: binary_sensor.guest_mode
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
          entity_id: input_boolean.summer_mode
          value: "on"
```

---

## 7. Notifications Setup

### 7.1 Telegram – Mode A (via HA Notify)

Mode A uses the standard `notify` service already configured in HA:

1. Set up the [Telegram bot integration](https://www.home-assistant.io/integrations/telegram/) in HA.
2. In ATC Config Flow select **Telegram mode: mode_a**.
3. Enter the `notify` service name, e.g. `notify.telegram_user`.

Notification template variables: `{{ name }}`, `{{ time_until }}`, `{{ reason }}`.

### 7.2 Telegram – Mode B (Direct Bot)

Mode B sends messages directly without the HA Telegram integration:

1. Create a Telegram bot via [@BotFather](https://t.me/botfather) and copy the token.
2. Find your chat ID (send a message to `@userinfobot`).
3. In ATC Config Flow select **Telegram mode: mode_b**.
4. Enter **Bot Token** and **Chat ID**.

### 7.3 Voice Notifications

| Provider | Notes |
|---|---|
| `alexa_media_player` | Requires [Alexa Media Player](https://github.com/custom-components/alexa_media_player) |
| `google_cast` | Uses `tts` service + Cast |
| `sonos` | Uses Sonos TTS |
| `generic_tts` | Any HA TTS service + media player |

Configure in Config Flow → **Voice provider** and enter the target media player entity.

### 7.4 Notification Escalation

To repeat a notification until acknowledged:

```yaml
service: advanced_timer_calendar.create_reminder
data:
  title: "Take medication"
  due_time: "08:00:00"
  escalation:
    enabled: true
    interval_minutes: 15
    max_escalations: 4
```

Acknowledge via:
```yaml
service: advanced_timer_calendar.acknowledge_notification
data:
  item_id: "abc123"
  item_type: reminder
```

---

## 8. Dashboard & Lovelace Cards

### 8.1 Timer Overview Card

```yaml
type: entities
title: My Timers
entities:
  - entity: switch.atc_main_morning_garden_lights
  - entity: sensor.atc_main_morning_garden_lights_next_run
```

### 8.2 Calendar Card

The built-in HA calendar card works with the ATC calendar entity:

```yaml
type: calendar
entities:
  - calendar.atc_main
initial_view: dayGridMonth
```

### 8.3 To-Do Card

```yaml
type: todo-list
entity: todo.atc_main
```

### 8.4 Custom Button Card for Run Now

```yaml
type: button
name: "Run Irrigation Now"
tap_action:
  action: call-service
  service: advanced_timer_calendar.run_now
  service_data:
    timer_id: "YOUR_TIMER_ID"
```

---

## 9. External Calendar Integration

### 9.1 Microsoft 365 / Outlook

```yaml
service: advanced_timer_calendar.add_calendar_account
data:
  provider: microsoft
  name: "Work Calendar"
  client_id: "your-azure-app-client-id"
  client_secret: "your-secret"
  tenant_id: "your-tenant-id"
  sync_direction: bidirectional
```

### 9.2 Google Calendar

```yaml
service: advanced_timer_calendar.add_calendar_account
data:
  provider: google
  name: "Personal Google"
  client_id: "your-google-client-id"
  client_secret: "your-google-secret"
  sync_direction: inbound
```

### 9.3 Apple iCloud

```yaml
service: advanced_timer_calendar.add_calendar_account
data:
  provider: apple
  name: "iCloud"
  username: "apple-id@icloud.com"
  password: "app-specific-password"
  sync_direction: inbound
```

### 9.4 Manual Sync

```yaml
service: advanced_timer_calendar.sync_calendar
data:
  account_id: "abc123"
```

### 9.5 Conflict Resolution

Set `conflict_strategy` to:
- `ha_wins` – local ATC data takes precedence
- `remote_wins` – remote calendar takes precedence
- `newest_wins` – most recently modified entry wins
- `manual` – conflicts are flagged for manual resolution

---

## 10. HA Services Reference

| Service | Description | Key Parameters |
|---|---|---|
| `create_timer` | Create a new timer | `name`, `schedule_type`, `time`, `actions` |
| `update_timer` | Modify an existing timer | `timer_id`, any updatable field |
| `delete_timer` | Remove a timer | `timer_id` |
| `enable_timer` | Enable a disabled timer | `timer_id` |
| `disable_timer` | Disable without deleting | `timer_id` |
| `pause_timer` | Pause execution temporarily | `timer_id` |
| `skip_next` | Skip the next scheduled run | `timer_id` |
| `run_now` | Trigger a timer immediately | `timer_id` |
| `create_reminder` | Create reminder/to-do | `title`, `due_date`, `due_time` |
| `complete_todo` | Mark to-do as done | `reminder_id` |
| `sync_calendar` | Trigger external calendar sync | `account_id` (optional) |
| `add_calendar_account` | Add external calendar | `provider`, `name`, credentials |
| `remove_calendar_account` | Remove external calendar | `account_id` |
| `create_external_event` | Create event on external calendar | `account_id`, `title`, `start`, `end` |
| `delete_external_event` | Delete event on external calendar | `account_id`, `event_id` |
| `create_calendar_trigger` | Fire HA event from calendar entry | `account_id`, `filter`, `event_name` |
| `delete_calendar_trigger` | Remove calendar trigger | `trigger_id` |

---

## 11. FAQ & Troubleshooting

### Timer is not firing

1. Check the switch entity is **on** (`switch.atc_<name>_<timer_name>`).
2. Verify the `time` field uses 24-hour format `HH:MM:SS`.
3. Check conditions – an unsatisfied condition silently skips execution.
4. Review logs: *Settings → System → Logs*, filter for `advanced_timer_calendar`.

### Smart Watering always skips

- Verify the sensor entity IDs are correct and the sensors are not `unavailable`.
- Check `rain_probability_threshold`: the weather entity must provide `forecast[0].precipitation_probability` as a value 0–100.

### Notifications not received

- **Telegram Mode A**: confirm the `notify` service name exists in HA and test it manually.
- **Telegram Mode B**: verify the bot token and chat ID. Check if the bot has been started (send `/start`).
- **Voice**: ensure the media player entity is available and not muted.

### Import/Export

Export all data:
```yaml
service: advanced_timer_calendar.export_all
```
The result is returned in the service response. Copy the JSON and store it safely.

Import:
```yaml
service: advanced_timer_calendar.import_json
data:
  json_str: '{"atc_export_version":"1.0","timers":[...]}'
  merge: true
```

### Getting execution statistics

```yaml
service: advanced_timer_calendar.get_timer_stats
data:
  timer_id: "abc123"
  days: 30
```

Returns: `total_executions`, `fired`, `skipped`, `errors`, `skip_rate`, `avg_duration_seconds`, `last_fired`.

### Resetting / clearing history

```yaml
service: advanced_timer_calendar.clear_timer_history
data:
  timer_id: "abc123"   # omit to clear all history
```
