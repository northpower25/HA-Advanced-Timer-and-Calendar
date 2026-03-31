# Concept: HA Advanced Timer & Calendar

## 1. Overview & Goals

A custom component for Home Assistant covering the following core areas:

- **Timer / Scheduler**: Control entities (switches, lights, etc.) on a schedule
- **Reminder / Calendar**: Reminders, appointments, anniversaries, to-dos
- **Telegram Integration**: Notifications and bidirectional bot control (interactive when HA Telegram Bot is present)
- **Voice Notifications**: Spoken timer and reminder notifications via Alexa Media Player, Google Home/Cast, Sonos, or any HA TTS-compatible media player – with predefined and freely configurable voice message templates
- **Bidirectional Calendar Integration**: Full synchronisation with Microsoft 365/Outlook, Google Calendar and Apple iCloud Calendar – for multiple persons/accounts simultaneously
- **Persistence**: All data survives HA restarts
- **User-Friendliness**: Full configuration via the HA UI (Config Flow + Options Flow)
- **Multi-instance**: Multiple independent instances supported in parallel (e.g. "Garden", "House")
- **Own Dashboard + Lovelace Cards**: A bundled dashboard and standalone cards for custom dashboards
- **HACS-compliant**: HACS-compatible from the start, easy installation and updates

**Minimum requirement**: Home Assistant 2026.0+

---

## 2. Architecture

### 2.1 Component Structure

```
custom_components/advanced_timer_calendar/
├── __init__.py              # Setup, Coordinator startup, multi-instance support
├── manifest.json            # Metadata, dependencies (HACS-compliant)
├── config_flow.py           # Setup wizard (UI), multi-instance
├── options_flow.py          # Post-setup settings
├── const.py                 # Constants, enums, DOMAIN
├── coordinator.py           # Central DataUpdateCoordinator
├── storage.py               # Persistence via HA Storage API (with migration engine)
├── scheduler.py             # Timer logic & scheduling engine
├── calendar.py              # Calendar platform (CalendarEntity)
├── sensor.py                # Sensor platform (status, next trigger)
├── switch.py                # Switch platform (timer on/off)
├── services.yaml            # HA service definitions
├── services.py              # Service handlers
├── telegram_bot.py          # Telegram notification & control module
│                            # (interactive/bidirectional via HA telegram_bot)
├── voice_notifications.py   # Voice notification module
│                            # (Alexa Media Player, Google Home/Cast, Sonos, HA TTS)
├── external_calendars/
│   ├── __init__.py          # Package init, provider registry
│   ├── base.py              # Abstract base class CalendarProvider
│   ├── microsoft.py         # Microsoft 365 / Outlook (Graph API)
│   ├── google.py            # Google Calendar API
│   ├── apple.py             # Apple iCloud Calendar (CalDAV)
│   ├── sync_engine.py       # Bidirectional sync logic & conflict resolution
│   ├── trigger_processor.py # Event-based HA trigger evaluation
│   └── oauth_handler.py     # OAuth2 flows (PKCE, Device Code)
├── translations/
│   ├── de.json
│   └── en.json
├── strings.json
└── www/                     # Lovelace Custom Cards (HACS frontend)
    ├── atc-timer-card.js    # Timer overview card
    ├── atc-reminder-card.js # Calendar/reminder card
    └── atc-status-card.js   # System status card

hacs.json                    # HACS manifest (repo root)
dashboard/
└── atc_dashboard.yaml       # Bundled default dashboard
```

### 2.2 Data Storage

**HA Storage API** (`.storage/advanced_timer_calendar`) – JSON file written on every change. No data loss on restart.

Data structure (simplified):

```json
{
  "version": 1,
  "schema_version": 1,
  "timers": [ { "...Timer object..." } ],
  "reminders": [ { "...Reminder object..." } ],
  "calendar_accounts": [
    {
      "id": "uuid",
      "provider": "microsoft|google|apple",
      "display_name": "John Doe – Work",
      "credentials": { "...OAuth token (encrypted)..." },
      "calendars": [
        {
          "remote_id": "...",
          "name": "Calendar name",
          "sync_enabled": true,
          "sync_direction": "bidirectional|inbound|outbound",
          "color": "#0078d4"
        }
      ]
    }
  ],
  "calendar_triggers": [ { "...Trigger object..." } ],
  "settings": { "...global settings..." }
}
```

### 2.3 Storage Schema Migration

The storage file contains the field `schema_version`. On every startup the integration compares the stored version against the current version constant:

```python
STORAGE_VERSION = 1  # In const.py – increment on breaking changes
```

**Migration engine** (`storage.py`):
- On load: read `schema_version` from file
- If `schema_version < STORAGE_VERSION`: apply migration functions sequentially
- Each migration is a dedicated function (`migrate_v1_to_v2`, `migrate_v2_to_v3`, …)
- After successful migration: write data back with the new `schema_version`
- On error: create backup of the old file at `.storage/advanced_timer_calendar.bak`, log error

**Example migration (v1 → v2)**:
```python
def migrate_v1_to_v2(data: dict) -> dict:
    # Example: add new required field 'tags' to all timers
    for timer in data.get("timers", []):
        timer.setdefault("tags", [])
    data["schema_version"] = 2
    return data
```

---

## 3. Timer / Scheduler

### 3.1 Timer Object (Data Model)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique ID |
| `name` | string | Display name |
| `enabled` | bool | Active / inactive |
| `schedule_type` | enum | `once`, `daily`, `weekdays`, `interval`, `yearly` |
| `time` | time | Trigger time (None = all-day) |
| `all_day` | bool | All-day event |
| `weekdays` | list[int] | 0=Mon…6=Sun |
| `interval_value` | int | e.g. 2 |
| `interval_unit` | enum | `days`, `weeks`, `months` |
| `start_date` | date | Start date |
| `end_date` | date\|None | End date (None = unlimited) |
| `actions` | list | Actions on trigger |
| `conditions` | list | Conditions (entities, time windows) |
| `duration` | int\|None | Duration in seconds (e.g. irrigation 10 min) |
| `notification` | dict\|None | Notification config |

### 3.2 Schedule Types

| Type | Description | Example |
|------|-------------|---------|
| `once` | One-time | Tomorrow 07:00 |
| `daily` | Every day | Every day 06:30 |
| `weekdays` | Specific weekdays | Mon, Wed, Fri 08:00 |
| `interval` | Every X days/weeks/months | Every 3 days |
| `yearly` | Annually | Every year on June 1st |
| `cron` | Advanced users (optional) | Cron expression |

### 3.3 Actions (Action Objects)

Each action consists of:

- **Target**: Entity ID(s) (e.g. `switch.garden_valve_1`) – multiple targets supported
- **Action**: `turn_on`, `turn_off`, `toggle`, `set_value`, HA service call
- **Delay**: Optional delay after trigger (e.g. irrigation sector 2 starts 5 min after sector 1)
- **Duration**: Automatic turn-off after X seconds/minutes

**Irrigation example:**

```
Trigger: daily 06:00
Action 1: switch.valve_zone_1 → ON, duration 10 min
Action 2: switch.valve_zone_2 → ON, delay 10 min, duration 8 min
Action 3: switch.valve_zone_3 → ON, delay 18 min, duration 12 min
```

### 3.4 Conditions

Conditions block the timer trigger when not met. Multiple conditions can be linked via AND/OR logic.

- **Entity state**: e.g. `sensor.rain_sensor == 'raining'` → skip timer
- **Time window**: Only execute between 06:00–20:00
- **Numeric threshold**: e.g. `sensor.soil_moisture < 30` (less than / greater than value)
- **Numeric range (from/to)**: e.g. `sensor.outdoor_temperature` between `10°C` and `25°C`
- **Template**: Any HA template

#### Condition Object (Data Model)

| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | string | Entity to evaluate |
| `condition_type` | enum | `state`, `numeric_below`, `numeric_above`, `numeric_between`, `template` |
| `value` | any\|None | Comparison value (for `state`, `numeric_below`, `numeric_above`) |
| `min_value` | float\|None | Lower bound (only for `numeric_between`) |
| `max_value` | float\|None | Upper bound (only for `numeric_between`) |
| `logic_operator` | enum | `and` / `or` – how this condition links to the next |
| `template` | string\|None | HA template expression (only for `template`) |

**Examples:**
```yaml
# Outdoor temperature between 10°C and 30°C:
entity_id: sensor.outdoor_temperature
condition_type: numeric_between
min_value: 10
max_value: 30

# Outdoor temperature below 5°C:
entity_id: sensor.outdoor_temperature
condition_type: numeric_below
value: 5
```

#### 3.4.1 Hold Timer

Each condition can be assigned a **hold time**: the measured state must be continuously satisfied for at least the specified duration before the timer event fires. This prevents false triggers from short-term measurement fluctuations (e.g. brief temperature spikes).

| Field | Type | Description |
|-------|------|-------------|
| `hold_seconds` | int\|None | Minimum duration in seconds (0 = immediate, `None` = no hold) |

**Example:** Outdoor temperature below 0°C **for at least 10 minutes** → activate frost protection (`hold_seconds: 600`).

### 3.5 Scheduling Engine

- `asyncio`-based, runs in the HA event loop
- Next execution time is calculated at startup and registered via an `async_track_point_in_time` callback
- After each trigger: calculate next time and re-register callback
- On HA restart: load all timers from storage and re-register callbacks

---

## 4. Reminder / Calendar

### 4.1 Reminder Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique ID |
| `title` | string | Title |
| `description` | string | Description |
| `type` | enum | `reminder`, `todo`, `anniversary`, `appointment` |
| `date` | date | Date |
| `time` | time\|None | Time (None = all-day) |
| `recurrence` | dict\|None | Recurrence rule |
| `reminder_before` | int | Lead time for notification (minutes) |
| `tags` | list[str] | Categories / tags |
| `completed` | bool | For to-dos: completed |
| `notification` | dict\|None | Notification config |

### 4.2 Calendar Platform

Implemented as a `CalendarEntity` – this makes the integration appear in the HA calendar and be fully compatible with the HA Calendar dashboard.

Separate calendars (as individual entities) per type:

- `calendar.atc_appointments` – Appointments
- `calendar.atc_anniversaries` – Anniversaries
- `calendar.atc_todos` – To-dos
- `calendar.atc_timer_schedule` – Overview of all timer triggers

### 4.3 To-Do Integration

Optional integration with HA's native `todo` platform (from HA 2023.11) for native to-do lists in the dashboard.

---

## 5. Notifications & Telegram Integration

### 5.0 Notification Channels

One or more notification channels can be independently enabled per timer/appointment:

| Channel | Description |
|---------|-------------|
| **Telegram (Mode A)** | Directly via Bot Token – outbound messages only |
| **Telegram (Mode B)** | Via HA `telegram_bot` – bidirectional & interactive with inline keyboards |
| **HA Notify** | Any HA notification service (e.g. `notify.mobile_app_phone`, `notify.pushover`, email notify, etc.) |
| **Voice Notification** | Spoken announcements on Alexa, Google Home/Cast, Sonos, or other HA TTS-capable devices |

Channels can be combined, e.g. Telegram **and** HA Notify **and** Voice Notification simultaneously for the same timer.

### 5.1 Operating Modes (Telegram)

**Mode A – Standalone** (simple): Enter Bot Token + Chat ID directly in the Config Flow → the integration sends messages itself via the Telegram Bot API. Outbound notifications only, no inbound commands.

**Mode B – HA Telegram Bot** (advanced, recommended): Use the existing `telegram_bot` integration in HA. When present, **bidirectional and interactive** communication is enabled:
- Outbound: messages and inline keyboards via `notify.<telegram_service>`
- Inbound: commands and callback responses via HA events (`telegram_command`, `telegram_callback`)
- Interactive inline keyboards for confirmations, selections, and status queries

### 5.2 Notification Timing

For each timer/appointment up to **three notification points** can be independently enabled or disabled:

| # | Timing | Configuration |
|---|--------|--------------|
| **1** | **Before** – before the timer/appointment becomes active | Time period in minutes, hours, days, or weeks before activation |
| **2** | **After** – after the timer/appointment has become active | Time period in minutes, hours, days, or weeks after activation |
| **3** | **Completion** – when a timer event has finished and the timer has been reset | No additional time configuration needed |

**Notification config data model (`notification`):**

```json
{
  "channels": ["telegram", "ha_notify", "voice"],
  "ha_notify_service": "notify.mobile_app_iphone",
  "voice": {
    "enabled": true,
    "provider": "alexa_media_player",
    "media_player_entity": "media_player.echo_dot_kitchen",
    "volume": 0.6,
    "tts_engine": null,
    "language": "en-US"
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
    "before": "⏰ {{ name }} starts in {{ time_until }}.",
    "after": "✅ {{ name }} has started.",
    "reset": "🔄 {{ name }} has completed and been reset.",
    "skipped": "⏭ {{ name }} was skipped ({{ reason }}).",
    "voice_before": "{{ name }} starts in {{ time_until }}.",
    "voice_after": "{{ name }} has started.",
    "voice_reset": "{{ name }} has completed.",
    "voice_skipped": "{{ name }} was skipped."
  }
}
```

**Supported time units (`unit`):** `minutes`, `hours`, `days`, `weeks`

**Trigger occasions:**

- Timer fires – start (before & after)
- Timer fires – end / reset (completion notification)
- Condition prevents execution ("Irrigation skipped – rain detected")
- Reminder/appointment coming up soon
- To-do due
- Error / timer disabled

### 5.3 Notification Texts & Templates

The texts for all notification timing points are **automatically suggested** and can be individually customised per timer/appointment. Default templates are defined in `translations/de.json` and `translations/en.json`.

**Default templates (examples):**

| Timing | Default text |
|--------|-------------|
| Before activation | `⏰ [Timer name] starts in [time period].` |
| After activation | `✅ [Timer name] has started. Duration: [duration] min.` |
| Completion/reset | `🔄 [Timer name] has completed and been reset.` |
| Skipped | `⏭ [Timer name] was skipped. Reason: [condition].` |
| Reminder | `🔔 Reminder: [Title] in [time period].` |

**Template variables** (usable in all texts): `{{ name }}`, `{{ time_until }}`, `{{ duration }}`, `{{ reason }}`, `{{ next_run }}`, `{{ entity_states }}`.

Templates are displayed in the ATC UI when configuring a timer/appointment and can be edited directly and tested before saving.

### 5.4 Bot Control (Mode B – HA Telegram Bot)

Control timers via Telegram commands (only when `telegram_bot` integration is present):

| Command | Function |
|---------|---------|
| `/timer list` | Show all timers |
| `/timer pause Garden` | Pause timer |
| `/timer resume Garden` | Resume timer |
| `/timer next Garden` | Show next run |
| `/reminder list` | Upcoming reminders |
| `/reminder add ...` | Quick-create reminder |
| `/status` | System overview |

**Inline keyboards (interactive, Mode B)**:

When a timer trigger or reminder fires, inline keyboard buttons are included in the message:

```
🌿 Irrigation Zone 1 starts in 5 minutes
[✅ Confirm] [⏭ Skip] [⏸ Pause (1h)]
```

```
🔔 Reminder: Doctor's appointment in 30 minutes
[✅ OK] [⏰ Remind in +15 min] [❌ Cancel]
```

Callback responses are processed via HA events (`telegram_callback`) and trigger the corresponding ATC services.

Security: Whitelist of chat IDs allowed to send commands.

---

## 5.5 Voice Notifications

ATC supports spoken announcements of timer and reminder notifications on smart speakers and other audio devices. Voice notification is a standalone, combinable channel (in addition to Telegram and HA Notify).

### Supported Integrations & Requirements

#### 🔔 Alexa Media Player (recommended for Amazon Echo devices)

> ⚠️ **Installation required**: The [Alexa Media Player](https://github.com/alandtse/alexa_media_player) integration must be installed separately via **HACS**. It is **not** part of Home Assistant Core.
> Installation link: **https://github.com/alandtse/alexa_media_player**

- Supported devices: Amazon Echo, Echo Dot, Echo Show, Echo Studio, Fire TV (with Alexa)
- How it works: ATC calls the notify service `notify.alexa_media_<device_name>` and sends the message text as `announce` type
- The message is spoken aloud on the selected Alexa device without permanently interrupting the current media
- Also supports groups (address multiple Echo devices simultaneously)
- Volume: controllable via the `data` field of the notify service payload

**Example service call (generated internally by ATC):**
```yaml
service: notify.alexa_media_echo_dot_kitchen
data:
  message: "Irrigation Zone 1 starts in 5 minutes."
  data:
    type: announce
    method: all
```

**Prerequisites:**
1. Install Alexa Media Player via HACS: https://github.com/alandtse/alexa_media_player
2. Sign in with your Amazon account in the Alexa Media Player integration
3. Echo devices are automatically discovered as `media_player.echo_*` entities

---

#### 🏠 Google Home / Google Cast (native in HA)

> ✅ **No additional installation needed** – The Google Cast integration is part of Home Assistant Core.

- Supported devices: Google Home, Google Home Mini/Nest Mini, Nest Hub, Nest Hub Max, Chromecast Audio, any Google Cast-capable device
- How it works: ATC uses HA's built-in `tts.speak` service with a Google Cast `media_player`
- TTS engine: Configurable (default: `tts.google_translate_say` or `tts.cloud_say` via HA Cloud)

**Example service call:**
```yaml
service: tts.speak
data:
  media_player_entity_id: media_player.google_home_living_room
  message: "Irrigation Zone 1 starts in 5 minutes."
  options:
    voice: en-US-Standard-A
```

---

#### 🎵 Sonos (native in HA)

> ✅ **No additional installation needed** – The Sonos integration is part of Home Assistant Core.

- Supported devices: All Sonos speakers (Era, Move, Roam, One, Five, Arc, Beam, Ray, etc.)
- How it works: `tts.speak` service with a Sonos `media_player`
- TTS engine: Configurable (Piper/local, HA Cloud TTS, Google Translate TTS)
- Supports volume control before/after announcement and restoring the previous playback state

---

#### 🔊 HA TTS + Any Media Player (generic)

> ✅ **No additional installation needed** – Works with any `media_player` entity integrated into HA.

- How it works: ATC uses the `tts.speak` service with the media player entity and TTS engine selected in the Config Flow
- Compatible with: VLC Media Player, ESPHome Speaker, Squeezebox/Logitech Media Server, Kodi, and all other HA `media_player` entities
- **Available TTS engines (selection):**

| TTS Engine | Type | Requirement | Quality |
|-----------|------|-------------|---------|
| **Piper** (local) | Local | Wyoming protocol / add-on | ⭐⭐⭐⭐ – Offline, private, free |
| **HA Cloud TTS** | Cloud | Nabu Casa subscription | ⭐⭐⭐⭐⭐ – Very natural (Azure Neural) |
| **Google Translate TTS** | Cloud | None (free) | ⭐⭐⭐ – Simple, no configuration needed |
| **Microsoft Azure TTS** | Cloud | Azure account + API key | ⭐⭐⭐⭐⭐ – Very natural |
| **Amazon Polly** | Cloud | AWS account + API key | ⭐⭐⭐⭐ – Natural |
| **ElevenLabs** | Cloud | API key (paid) | ⭐⭐⭐⭐⭐ – Very natural |

---

### Configuration in the Config Flow (Step: Voice Notifications)

Voice notification is offered as an optional step in the ATC Config Flow:

```
┌─────────────────────────────────────────────────────────────────┐
│  Voice Notifications (optional)                                 │
│                                                                 │
│  Integration / Provider:                                        │
│  ○ Alexa Media Player ⚠️ HACS installation required            │
│  ○ Google Home / Google Cast                                    │
│  ○ Sonos                                                        │
│  ○ HA TTS + Media Player (generic)                             │
│  ○ No voice channel                                             │
│                                                                 │
│  [For Alexa Media Player:]                                      │
│  Media player entity:   [media_player.echo_dot_kitchen ▾]      │
│  Volume:                [████░░░░░░] 60%                        │
│  Announce mode:         ○ announce  ○ tts                       │
│                                                                 │
│  [For Google / Sonos / generic:]                                │
│  Media player entity:   [media_player.google_home_living ▾]    │
│  TTS engine:            [tts.cloud_say ▾]                       │
│  Language:              [en-US ▾]                               │
│  Volume:                [████░░░░░░] 60%                        │
│                                                                 │
│  Default voice templates: (editable)                            │
│  Before:      "{{ name }} starts in {{ time_until }}."          │
│  After:       "{{ name }} has started."                         │
│  Completion:  "{{ name }} has completed."                       │
│  Reminder:    "Reminder: {{ title }} in {{ time_until }}."      │
│                                                                 │
│  [Play test announcement]    [Continue]                         │
└─────────────────────────────────────────────────────────────────┘
```

> ⚠️ **Note on Alexa Media Player**: To use this feature, the [Alexa Media Player](https://github.com/alandtse/alexa_media_player) integration must be installed and configured via HACS. Without this integration, Alexa devices will not appear as selectable entities.

---

### Predefined Voice Text Templates

Separate, TTS-optimised voice text templates exist for each notification timing point (no emojis, shorter than written text messages):

| Timing | Predefined voice text |
|--------|----------------------|
| Before | `{{ name }} starts in {{ time_until }}.` |
| After activation | `{{ name }} has started. Duration: {{ duration }} minutes.` |
| Completion/reset | `{{ name }} has completed.` |
| Skipped | `{{ name }} was skipped. Reason: {{ reason }}.` |
| Reminder | `Reminder: {{ title }} in {{ time_until }}.` |
| Error/disabled | `Timer {{ name }} is disabled or has an error.` |

Templates can be individually customised per timer/appointment. Template variables are identical to those for written notifications: `{{ name }}`, `{{ time_until }}`, `{{ duration }}`, `{{ reason }}`, `{{ title }}`, `{{ next_run }}`.

---

### Data Model: Voice Configuration (`voice`)

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Voice channel active/inactive |
| `provider` | string | `alexa_media_player`, `google_cast`, `sonos`, `generic_tts` |
| `media_player_entity` | string | HA entity ID of the target device (e.g. `media_player.echo_dot_kitchen`) |
| `media_player_entities` | list[str] | Optional: multiple simultaneous devices (group) |
| `volume` | float | Volume 0.0–1.0 (default: 0.5) |
| `restore_volume` | bool | Restore volume after announcement (default: `true`) |
| `tts_engine` | string\|None | TTS service (e.g. `tts.cloud_say`, `tts.piper`); for Alexa: `null` |
| `language` | string\|None | Language code (e.g. `en-US`, `de-DE`); for Alexa: `null` |
| `announce_mode` | string | Alexa-specific: `announce` (briefly interrupts) or `tts` (waits for completion) |

---

### Overview: Voice Notification Integrations

| Integration | Device types | Installation | Requires TTS engine | Recommendation |
|-------------|-------------|-------------|---------------------|----------------|
| **Alexa Media Player** | Amazon Echo, Echo Dot, Echo Show, Echo Studio | ⚠️ HACS ([Link](https://github.com/alandtse/alexa_media_player)) | No (Alexa built-in) | ⭐⭐⭐⭐⭐ Best solution for Alexa users |
| **Google Home / Cast** | Google Home, Nest Mini/Hub, Chromecast Audio | ✅ HA Core | Yes (e.g. `tts.cloud_say`) | ⭐⭐⭐⭐⭐ Best solution for Google users |
| **Sonos** | All Sonos speakers | ✅ HA Core | Yes | ⭐⭐⭐⭐ Great for Sonos users |
| **HA TTS + Media Player** | Any (VLC, ESPHome, Kodi…) | ✅ HA Core | Yes | ⭐⭐⭐ Universal |

---

| Entity | Type | Description |
|--------|------|-------------|
| `switch.atc_<name>` | Switch | Enable/disable timer |
| `sensor.atc_<name>_next_run` | Sensor | Next run (timestamp) |
| `sensor.atc_<name>_last_run` | Sensor | Last run |
| `sensor.atc_<name>_status` | Sensor | `idle`, `running`, `paused`, `skipped` |
| `calendar.atc_*` | Calendar | Calendar views |

---

## 7. HA Services

| Service | Parameters | Description |
|---------|-----------|-------------|
| `atc.create_timer` | name, schedule, actions | Create timer |
| `atc.update_timer` | timer_id, ... | Update timer |
| `atc.delete_timer` | timer_id | Delete timer |
| `atc.enable_timer` | timer_id | Enable timer |
| `atc.disable_timer` | timer_id | Disable timer |
| `atc.pause_timer` | timer_id, duration | Temporarily pause |
| `atc.skip_next` | timer_id | Skip next run |
| `atc.run_now` | timer_id | Run immediately |
| `atc.create_reminder` | title, date, ... | Create reminder |
| `atc.complete_todo` | reminder_id | Mark to-do as completed |
| `atc.sync_calendar` | account_id | Trigger manual sync for account |
| `atc.add_calendar_account` | provider, display_name | Add a new calendar account |
| `atc.remove_calendar_account` | account_id | Remove account (including data) |
| `atc.create_external_event` | account_id, calendar_id, title, start, end, ... | Create event in external calendar |
| `atc.delete_external_event` | account_id, event_id | Delete event in external calendar |
| `atc.create_calendar_trigger` | name, account_id, keyword, lead_time, actions | Create calendar trigger |
| `atc.delete_calendar_trigger` | trigger_id | Delete calendar trigger |

---

## 8. Config Flow (Setup Wizard)

### Step 1 – General
- Name of the integration instance

### Step 2 – Telegram (optional)
- Mode: "No Telegram", "Own Bot", "HA Telegram Bot"
- For "Own Bot": Bot Token, Chat ID, send test message
- For "HA Telegram Bot": Select existing notification service

### Step 2b – Voice Notifications (optional)
- Select integration: "No voice channel", "Alexa Media Player", "Google Home / Cast", "Sonos", "HA TTS + Media Player (generic)"
- **Alexa Media Player**: Select `media_player.echo_*` entity, volume (0–100 %), announce mode (`announce` / `tts`)
  > ⚠️ Note: Alexa Media Player must be installed via HACS → https://github.com/alandtse/alexa_media_player
- **Google Home / Cast, Sonos, generic**: Select `media_player.*` entity, TTS engine (from available HA TTS services), language, volume
- Edit default voice text templates (before, after, completion, reminder)
- Test announcement: "Play test announcement" sends a sample message immediately to the selected device

### Step 3 – External Calendar Accounts (optional, repeatable)
- Select provider: Microsoft 365 / Outlook, Google Calendar, Apple iCloud Calendar
- **Microsoft 365**: OAuth2 Device Code Flow (opens browser with code) → user signs in at Microsoft → token is stored
- **Google**: OAuth2 Authorization Code Flow with PKCE → redirects to local HA callback → token is stored
- **Apple / iCloud**: Enter Apple ID + app-specific password (no OAuth, CalDAV-based)
- Display name for the account (e.g. "John Work", "Family")
- After authentication: fetch available calendars and present for selection
- Per calendar: set sync direction (`Bidirectional`, `Inbound only`, `Outbound only`)
- Multiple accounts of the same provider are supported (e.g. two Google accounts)
- Configure sync interval (recommended: every 5–15 minutes; push notifications where available)

### Step 4 – Default Settings
- Default lead time for reminder notifications
- Time zone (default: HA time zone)

### Options Flow
All settings can be changed afterwards.

---

## 9. Frontend / UI

### 9.1 Native HA UI
- Config Flow & Options Flow → fully usable via HA UI
- Entities appear in the HA dashboard
- Calendar in the HA Calendar dashboard

### 9.2 Own ATC Dashboard (Phase 1)

A pre-configured dashboard (`dashboard/atc_dashboard.yaml`) is bundled with the integration and automatically registered in HA during initial setup. The dashboard exclusively uses ATC Lovelace Cards (see 9.3) and provides an immediate, complete overview:

- **Tab 1 – Timers**: All timers with status, next run time, on/off switches
- **Tab 2 – Calendar & Reminders**: Monthly view, upcoming appointments, to-do list
- **Tab 3 – External Calendars**: Sync status for all accounts, upcoming events
- **Tab 4 – Settings**: Quick access to Options Flow, notification test

The dashboard can be disabled or customised at any time. Recreating it is possible via a service call.

### 9.3 Lovelace Custom Cards (Phase 1)

All cards are delivered as standalone JavaScript modules (`www/`) and registered automatically via HACS. They can be used both in the ATC dashboard and in any user-defined dashboard:

#### ATC Timer Card (`atc-timer-card`)
```yaml
type: custom:atc-timer-card
instance: garden        # Optional: ATC instance name (for multiple instances)
show_disabled: false    # Hide disabled timers
```
- Overview of all timers for the instance
- Inline on/off toggle per timer
- Next run as countdown
- Status display: `idle`, `running`, `paused`, `skipped`
- Quick actions: Run now, Skip, Pause

#### ATC Reminder Card (`atc-reminder-card`)
```yaml
type: custom:atc-reminder-card
instance: garden
days_ahead: 7           # Days ahead to display
show_completed: false
```
- List view of upcoming reminders and appointments
- Colour-coded by type (appointment, anniversary, to-do)
- Inline completion of to-dos

#### ATC Status Card (`atc-status-card`)
```yaml
type: custom:atc-status-card
instance: garden
```
- System overview: active timers, upcoming reminders, sync status
- Telegram connection status
- Last / next actions

---

## 10. Technical Decisions

### Resolved Decisions (all open questions answered)

| Topic | Decision |
|-------|----------|
| **Minimum HA version** | HA 2026.0+ (stable Calendar, ToDo & Event API) |
| **Multiple instances** | ✅ Yes – via `config_entries`, unlimited instances (e.g. "Garden", "House") |
| **Dependencies** | HA-internal tools only, or libraries bundled with the integration (no separate PyPI installations required) |
| **Storage migration** | Versioned schema (`schema_version`), sequential migration functions in `storage.py` (see section 2.3) |
| **Telegram mode** | Mode A (standalone, outbound only) + Mode B (interactive & bidirectional when HA `telegram_bot` is present) |
| **Telegram bot commands** | Interactive inline keyboards for confirmations and selections in Mode B |
| **Irrigation logic** | Generic condition logic only (no dedicated irrigation engine) – extensible in later phases |
| **Lovelace cards** | ✅ Phase 1 – bundled as standalone custom cards (`www/`) + own dashboard |
| **HACS compatibility** | ✅ From the start – `hacs.json` in repo root, HACS-compliant directory structure |
| **UI languages** | German and English from the start (`translations/de.json` + `en.json`) |
| **Cron expressions** | Optional `cron` schedule type for advanced users (via bundled `croniter` library) |
| **OAuth2 app registration** | User registers their own app (Client ID/Secret entered in Config Flow) |
| **Token security** | AES-256 encryption via HA `secrets` / `keyring`, no plain text in storage |
| **Sync conflict resolution** | Configurable per account: `ha_wins`, `remote_wins`, `newest_wins`, `manual` |

### Recommended Design Decisions

- **Storage over SQLite**: HA Storage API is the idiomatic solution – no custom database schema
- **DataUpdateCoordinator**: Central state management, all platforms subscribe to it
- **Native asyncio**: No blocking calls, everything async
- **HACS from the start**: Enables easy distribution and updates for non-technical users
- **config_entries**: Multi-instance support via HA standard mechanism

### Open Questions (Account Type Restrictions)

Following the decision for user-registered OAuth apps (see above) and the introduction of account type distinctions, additional questions arise:

11. **OAuth2 registration strategy**: Should a central app registration be provided by the integration maintainer (recommended for personal users, since personal Microsoft accounts have no access to the Azure Portal), or should each user register their own app in the Azure Portal / Google Cloud Console? A central registration greatly simplifies setup for personal accounts, but may require app verification by Microsoft/Google and ongoing maintenance of the app registration.
12. **Detect Microsoft account type in setup**: Should the Config Flow explicitly distinguish between "Personal (outlook.com / hotmail.com)" and "Business (Microsoft 365 / Azure AD)" to automatically indicate available features and hide unavailable ones (e.g. Teams presence, Planner)?
13. **Handling of Business-only features in the UI**: Should features like Teams presence and Planner be visible in the Config Flow for all users (with a note "Only for Business accounts"), or should they be completely hidden when a personal account is detected?
14. **Google Cloud project guide for personal users**: Should a step-by-step guide for creating a Google Cloud application and OAuth Client ID be included in the documentation? This is mandatory for personal Gmail users without a central OAuth registration.
15. **Google app verification**: Google requires app verification (security assessment, privacy policy, domain verification) for sensitive scopes (Google Calendar) and restricted scopes (Gmail). Should a fully verified central app be pursued, or will only the use of individual (unverified) Client IDs be supported initially? With unverified apps, users see a Google security warning at login.
16. **Multiple notification channels**: Should multiple channels (e.g. Telegram AND HA Notify) be configurable simultaneously per timer/appointment, and should the channel selection be presented in the UI as a multi-select field or as individually togglable switches?
17. **Condition logic AND/OR groups**: Should condition linking only support simple flat AND/OR, or should nested groups (e.g. `(A AND B) OR C`) be possible? The latter greatly increases flexibility but also the complexity of the UI.
18. **YAML expert mode**: Should the YAML expert mode be a live editor with syntax highlighting (e.g. CodeMirror), or is a read-only view with copy and download functionality sufficient initially? Should edited YAML be importable directly as a timer configuration?


---

## 11. Own Ideas & Extensions

### 11.1 Irrigation Assistant "Smart Watering"
Automatic adjustment of irrigation duration based on:
- Temperature sensor
- Weather forecast (HA Weather entity)
- Soil moisture sensor

→ Algorithm calculates optimal duration.

### 11.2 "Vacation Mode"
Set all timers to "paused" for a defined period (with a single action).

### 11.3 Timer Templates / Presets
Pre-built timer templates for common use cases (irrigation, light timer, thermostat schedule) – especially helpful for non-technical users.

### 11.4 Sunrise/Sunset Trigger
Timers relative to sunrise/sunset (e.g. "Turn on outdoor lights 30 min before sunset").

### 11.5 Statistics & History
Sensor with number of executions, skipped executions, runtimes – as a basis for an HA Energy/Statistics dashboard.

### 11.6 Notification Escalation
If a reminder is not "acknowledged" (via Telegram button), remind again after X minutes.

### 11.7 Import/Export
Export and import timers and reminders as YAML/JSON – useful for backups and sharing configurations.

### 11.8 Expert Mode: YAML Code View & Export

For users with advanced HA knowledge it should be possible to view, edit, and export the **complete HA automation YAML** generated by the integration for any timer/appointment (including conditions, actions, and notifications).

**Features:**
- **View**: Per timer/appointment the equivalent HA automation YAML is displayed in the ATC UI with syntax highlighting.
- **Edit**: The YAML can be edited directly in the browser; changes can be applied back to the ATC configuration.
- **Export**: Download the YAML as a file or copy to clipboard for use in custom `automations.yaml` files.
- **Import**: Users can paste their own HA automation YAML which is then imported as an ATC timer/appointment (where supported).

**Example YAML (generated):**
```yaml
alias: "ATC: Garden Irrigation"
description: "Generated by ATC – Timer ID: abc-123"
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
      message: "✅ Irrigation Zone 1 complete."
mode: single
```

**UI integration**: Accessible via a "View / export YAML" button in the timer detail view of the ATC dashboard and in the `atc-timer-card`.

---

## 12. Phase Plan (Implementation Recommendation)

### Phase 1 – Core (MVP)
- HACS compliance (`hacs.json`, HACS-compliant structure)
- Persistence & storage (including migration engine)
- Multi-instance support via `config_entries`
- Scheduler engine (`daily`, `weekdays`, `interval`, `yearly`, `once`)
- Actions (`turn_on`, `turn_off`, duration per action/entity)
- Conditions (entity state, numeric below/above, numeric range from/to, template, AND/OR, hold timer)
- HA entities (switch, sensor)
- Config Flow (without Telegram, without external calendars)
- Calendar platform
- Services
- **Lovelace Custom Cards** (`atc-timer-card`, `atc-reminder-card`, `atc-status-card`)
- **ATC Dashboard** (automatically installed default dashboard)

### Phase 2 – Notifications, Telegram & Reminder
- Telegram Mode A (standalone, outbound only)
- Telegram Mode B (HA integration, bidirectional & interactive via inline keyboards)
- **HA Notify** as notification channel (in addition to Telegram, combinable)
- **Voice Notifications**:
  - Alexa Media Player (HACS, https://github.com/alandtse/alexa_media_player)
  - Google Home / Google Cast (native)
  - Sonos (native)
  - HA TTS + generic media player
  - Predefined & configurable voice text templates (TTS-optimised, no emojis)
  - Volume control, device selection, group announcements
- **Structured notification timing** (before, after, on completion/reset) with units minutes/hours/days/weeks
- **Customisable notification text templates** with proposed defaults (per timer/appointment)
- Reminder/calendar types (anniversaries, to-dos)
- HA To-Do platform integration
- Sunrise/sunset trigger
- Cron schedule type (for advanced users)

### Phase 3 – External Calendar Integration
- Google Calendar: OAuth2, bidirectional sync, calendar triggers
- Microsoft 365 / Outlook: Graph API, OAuth2 Device Code, bidirectional sync
- Apple iCloud Calendar: CalDAV, bidirectional sync
- Multi-account management in Config/Options Flow
- Configurable sync interval; Microsoft/Google webhook push support
- Calendar triggers: appointments as HA automation triggers
- Outbound sync: HA timers and reminders written to external calendars

### Phase 4 – Convenience & Extensions
- Smart watering algorithm (irrigation profile as extension of generic condition logic)
- Timer templates
- Import/export (YAML/JSON backup & sharing)
- **Expert mode: YAML code view, edit & export** (complete automation YAML per timer/appointment)
- Notification escalation
- Statistics & history
- Further Office integrations (Microsoft Teams presence, To Do, etc.)

---

## 13. HACS Configuration

### 13.1 hacs.json (Repo Root)

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

> **Note on dependencies**: Only HA-internal tools and libraries bundled with the integration are used. No external PyPI packages that need to be installed separately.

### 13.3 Directory Structure (HACS-compliant)

```
HA-Advanced-Timer-and-Calendar/          ← GitHub Repo Root
├── hacs.json                            ← HACS manifest
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
    └── atc_dashboard.yaml               ← Default dashboard
```

---

## 14. Bidirectional Calendar Integration (Microsoft 365 / Google / Apple)

### 14.1 Overview & Supported Providers

> **Note on account types**: This integration is primarily designed for **private accounts**. Features that are only available with Microsoft 365 Business/Work accounts (Azure AD) or Google Workspace are marked with 🏢 throughout sections 14 and 15. Features available to all account types are marked ✅. Features requiring additional setup are marked ⚠️.

| Provider | Protocol / API | Authentication | Account Types |
|----------|---------------|----------------|---------------|
| Microsoft 365 / Outlook | Microsoft Graph API (REST) | OAuth2 – Device Code Flow or Authorization Code Flow with PKCE | ✅ Personal (outlook.com) & 🏢 Business (M365) |
| Google Calendar | Google Calendar API v3 (REST) | OAuth2 – Authorization Code Flow with PKCE | ✅ Personal (gmail.com) & 🏢 Business (Workspace) |
| Apple iCloud Calendar | CalDAV (RFC 4791) | App-specific password (Apple ID + iCloud password alternative) | ✅ Personal & Business |
| Exchange Server (On-Premise) | EWS (Exchange Web Services) or CalDAV | NTLM / Basic Auth / Modern Auth | 🏢 Business only |

Multiple accounts of the same or different providers are fully supported. Each account is independently configurable.

### 14.2 Architecture: External Calendar Engine

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
│                         – Delta query for incremental sync
│                         – Microsoft Graph Webhooks (Change Notifications)
│
├── google.py            GoogleCalendarProvider
│                         – Google Calendar API v3
│                         – sync_token for incremental sync
│                         – Google Push Notifications (Webhook)
│
├── apple.py             AppleCalendarProvider
│                         – CalDAV via caldav library
│                         – CTags / ETags for incremental sync
│                         – No push, polling only
│
├── sync_engine.py       SyncEngine
│                         – Manages all accounts and their schedules
│                         – Incremental sync (delta/ETag-based)
│                         – Configurable conflict resolution strategy
│                         – Writes to HA Storage & external calendars
│
├── trigger_processor.py CalendarTriggerProcessor
│                         – Monitors incoming events for keywords/patterns
│                         – Calculates lead time and schedules HA triggers
│                         – Fires HA automation actions
│
└── oauth_handler.py     OAuthHandler
                          – Device Code Flow (Microsoft)
                          – Authorization Code + PKCE (Google, Microsoft)
                          – Automatic token refresh
                          – Tokens encrypted in HA Storage
```

### 14.3 Data Model: Calendar Account

```json
{
  "id": "uuid",
  "provider": "microsoft | google | apple | exchange",
  "display_name": "John Doe – Work",
  "owner_name": "John Doe",
  "credentials": {
    "access_token": "...(encrypted)...",
    "refresh_token": "...(encrypted)...",
    "token_expiry": "2026-04-01T10:00:00Z",
    "scope": ["Calendars.ReadWrite"]
  },
  "sync_interval_minutes": 10,
  "last_sync": "2026-03-29T15:00:00Z",
  "calendars": [
    {
      "remote_id": "AQMkAD...",
      "name": "Calendar",
      "color": "#0078d4",
      "sync_enabled": true,
      "sync_direction": "bidirectional",
      "ha_entity_id": "calendar.atc_ext_john_work_calendar",
      "delta_token": "...",
      "read_only": false
    }
  ]
}
```

### 14.4 Data Model: Calendar Trigger (Inbound → HA)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique ID |
| `name` | string | Display name of the trigger |
| `enabled` | bool | Active / inactive |
| `account_id` | UUID | Linked calendar account |
| `calendar_ids` | list[str] | Calendars to monitor (empty = all) |
| `keyword_filter` | string\|None | Keyword in title/description (e.g. `"#smarthome"`) |
| `tag_filter` | list[str] | Categories/tags on the calendar event |
| `lead_time_minutes` | int | Lead time before event start (0 = at start) |
| `also_at_end` | bool | Also fire when event ends |
| `actions` | list | HA actions to execute |
| `conditions` | list | Additional HA conditions |
| `entity_target` | string\|None | Directly controlled entity (quick config) |
| `notification` | dict\|None | Notification config |

**Example configuration:**
```
Name: "Activate home-office mode"
Account: John Work (Microsoft 365)
Calendar: Calendar (main calendar)
Keyword: "Home Office" (in title)
Lead time: 10 minutes
Action 1: light.office_lamp → turn_on, brightness 80%
Action 2: switch.monitor → turn_on
Action 3: climate.office → set_temperature 21°C
Also at end: Yes → Turn off all devices
```

### 14.5 Data Model: Outbound Sync Configuration (HA → External Calendar)

| Field | Type | Description |
|-------|------|-------------|
| `outbound_account_id` | UUID | Target account for outbound sync |
| `outbound_calendar_id` | string | Target calendar ID |
| `sync_timers` | bool | Export timer triggers as external events |
| `sync_reminders` | bool | Export reminders as external events |
| `sync_prefix` | string | Prefix for exported events (e.g. `"[HA]"`) |
| `include_description` | bool | Write timer details into event description |

### 14.6 Sync Engine: Technical Details

#### Incremental Synchronisation
- **Microsoft Graph**: `delta()` endpoint returns only changed/new/deleted events since last sync → `deltaLink` token is stored
- **Google Calendar**: `syncToken` saved after each sync response → next query returns only changes
- **Apple CalDAV**: Check calendar `CTag` for changes, then compare ETags of individual events

#### Push Notifications (Near-Realtime)
- **Microsoft Graph Webhooks**: Subscription on `/me/events` → callback URL (HA-internal webhook endpoint) → immediate notification on new/changed events
- **Google Push Notifications**: Channel on Google Calendar API → observe `X-Goog-Channel-Expiration` (max. 7 days, auto-renewal)
- **Apple CalDAV**: No push support → polling (configurable interval, default: 10 minutes)

#### Conflict Resolution (configurable per account)
| Strategy | Description |
|----------|-------------|
| `ha_wins` | On conflict, HA version overwrites external |
| `remote_wins` | On conflict, external version overwrites HA |
| `newest_wins` | Most recent `last_modified` timestamp wins |
| `manual` | Conflict is reported as sensor state, user resolves via service call |

#### Token Management
- Access token validity checked before every API call
- Automatic refresh via refresh token
- On failed refresh: set sensor state to `reauth_required` and send notification
- Tokens stored AES-256-encrypted in HA Storage API (key from `HA secret`)

### 14.7 HA Entities for External Calendars

| Entity | Type | Description |
|--------|------|-------------|
| `calendar.atc_ext_<account>_<calendar>` | Calendar | External calendar as HA CalendarEntity (read/write) |
| `sensor.atc_ext_<account>_sync_status` | Sensor | `ok`, `syncing`, `error`, `reauth_required` |
| `sensor.atc_ext_<account>_last_sync` | Sensor | Timestamp of last successful sync |
| `sensor.atc_ext_<account>_next_event` | Sensor | Next upcoming event (title + start time) |
| `binary_sensor.atc_ext_<account>_in_meeting` | Binary Sensor | `on` when an event is currently active |

### 14.8 Config Flow: Adding a Calendar Account (Step by Step)

```
1. Select provider: [Microsoft 365] [Google] [Apple iCloud] [Exchange]

── Microsoft 365 ──────────────────────────────────────────────
2. Enter display name: "Personal / Work / Family"
3. Start Device Code Flow:
   → Code is displayed: "Go to https://microsoft.com/devicelogin and enter: ABCD-EFGH"
   → Integration waits for authentication (timeout: 5 minutes)
   → On success: "✅ Successfully authenticated as john@contoso.com"
4. Calendar list is loaded → user selects calendars
5. Per calendar: sync direction (Bidirectional / Inbound only / Outbound only)

> ⚠️ **Note for personal account users (outlook.com / hotmail.com / live.com)**: Personal Microsoft accounts do not have access to the Azure Portal. Self-registering an OAuth app is therefore not possible without an Azure subscription. A central app registration by the integration maintainer is required, with "Personal Microsoft Accounts" explicitly enabled (→ Open Question 11). Features such as Teams presence and Planner are **not available** for personal accounts (→ Sections 15.1, 15.2).

── Google Calendar ────────────────────────────────────────────
2. Enter display name
3. OAuth2 Authorization URL is generated:
   → HA opens an internal callback endpoint on port 8123
   → User opens URL in browser → signs in to Google → grants permissions
   → After redirect: token automatically saved
4. Calendar list → select → sync direction

> ⚠️ **Note for personal account users (gmail.com)**: OAuth2 authentication requires a Client ID/Secret. Personal users must either create their own Google Cloud project and register an OAuth app (free but involved), or a central app registration provided by the maintainer can be used (→ Open Questions 11, 15). Unverified apps display a Google security warning at login.

── Apple iCloud ───────────────────────────────────────────────
2. Enter display name
3. Enter Apple ID (email)
4. Enter app-specific password (hint: https://appleid.apple.com → Security)
5. CalDAV server is discovered (automatically via DNS-SRV record)
6. Calendar list → select → sync direction
```

### 14.9 Demarcation from Existing HA Integrations

| Integration | Difference from ATC |
|-------------|---------------------|
| HA `google` (Google Calendar) | Read-only, no trigger processing, no outbound sync |
| HA `microsoft365` (via HACS) | No direct timer/reminder sync, no keyword triggers |
| HA native CalDAV | Read-only, no write support, no triggers |
| ATC (this concept) | Fully bidirectional, keyword triggers, multi-account, deeply integrated with timers/reminders |

### 14.10 Account Type Compatibility

The following table provides an overview of which features are available with which account type. **Personal accounts** (outlook.com, gmail.com, apple.com) are the primary target audience for this integration.

| Feature | Personal (Outlook.com) | Personal (Gmail) | 🏢 Business (M365) | 🏢 Business (Workspace) |
|---------|------------------------|------------------|--------------------|-------------------------|
| **Bidirectional calendar sync** | ✅ | ✅ | ✅ | ✅ |
| **Calendar triggers (keyword)** | ✅ | ✅ | ✅ | ✅ |
| **Graph/Push webhooks** | ✅ (max. 3 days) | ✅ (max. 7 days) | ✅ | ✅ |
| **Microsoft To Do sync** | ✅ | – | ✅ | – |
| **Google Tasks sync** | – | ✅ | – | ✅ |
| **Outlook email trigger** | ✅ | – | ✅ | – |
| **Gmail email trigger** | – | ⚠️ (*) | – | ✅ |
| **Send email (service)** | ✅ | ⚠️ (*) | ✅ | ✅ |
| **OneDrive backup** | ✅ (5 GB free) | – | ✅ (1 TB+) | – |
| **Teams presence** | ❌ | – | ✅ | – |
| **Microsoft Planner** | ❌ | – | ✅ | – |
| **SharePoint file trigger** | ❌ | – | ✅ | – |
| **Google Meet presence** | – | ✅ (**) | – | ✅ (**) |
| **Apple Calendar (CalDAV)** | ✅ | – | ✅ | – |
| **Apple Reminders (VTODO)** | ⚠️ (***) | – | ⚠️ (***) | – |

(*) Requires a Google Cloud project + Pub/Sub setup; for restricted scopes (Gmail) a Google app verification may be required for a central app registration.  
(**) No direct Google Meet API endpoint exists; meeting status is derived indirectly from Calendar events containing a Meet link – works equally for all account types.  
(***) Apple only partially supports VTODO via CalDAV; functionality may vary depending on the iCloud version.

---

## 15. Further Microsoft Office / Productivity Integrations

### 15.1 Microsoft Teams – Presence & Meeting Control 🏢 *(Microsoft 365 Business/Work account only)*

> ⚠️ **Account restriction**: The Graph Presence API (`/me/presence`) is exclusively available for Microsoft 365 Business/Work accounts (Azure AD / Entra ID). Personal Microsoft accounts (outlook.com, hotmail.com, live.com) have **no access** to this API. Microsoft Teams Consumer (personal version) does not support the Presence API. This feature is therefore only usable by users with a corporate account.

**Scenario**: When the user is in a Teams meeting → dim office light, turn on "Do Not Disturb" LED, silence doorbell notifications.

**Technical implementation**:
- Microsoft Graph API: `GET /me/presence` – returns presence status (`Available`, `Busy`, `InACall`, `InAMeeting`, `DoNotDisturb`, `Away`, `Offline`)
- Polling every 60 seconds or Graph Change Notifications on `/communications/presences`
- HA entities:
  - `sensor.atc_teams_presence_<name>` → value: `available`, `busy`, `in_meeting`, `dnd`, `away`, `offline`
  - `binary_sensor.atc_teams_in_meeting_<name>` → `on` when in a meeting
- HA automations can react to status changes

**Example automations**:
```
Meeting starts (InAMeeting):
  → light.office → dim to 30%
  → switch.dnd_light → ON
  → notify.family → "John is in a meeting until 15:00"

Meeting ends (Available):
  → light.office → 100%
  → switch.dnd_light → OFF
```

### 15.2 Microsoft To Do / Planner

**Microsoft To Do** ✅ *(Personal & Business)*:
- REST API: read/write task lists (`/me/todo/lists/{listId}/tasks`)
- Bidirectional sync with HA ToDo platform
- Due tasks as HA reminders → notification via Telegram
- Create new tasks from HA (via HA dashboard or service)

**Microsoft Planner** (team tasks) 🏢 *(Business only)*:
- Task status as HA sensor (e.g. project progress)
- Create new tasks on HA events (e.g. "Replace filter" when air quality sensor exceeds threshold)

> ⚠️ **Account restriction (Planner)**: Microsoft Planner is exclusively available with Microsoft 365 Business/Work accounts (Azure AD) and is not accessible to personal Outlook.com accounts.

### 15.3 Microsoft Outlook – Email Triggers

**Scenarios**:
- Email with subject keyword (e.g. "Package arrived") → fire HA action (notification, doorbell simulation)
- Email notifications for HA events (e.g. alarm alert) → send email via Graph API
- Unread emails as HA sensor (badge counter)

**Technical implementation**:
- Graph API: `/me/messages` with `$filter` and `$select`
- Graph Webhooks on inbox for near-realtime
- Service `atc.send_email`: send email via configured Outlook account

### 15.4 Microsoft OneDrive / SharePoint

**OneDrive Personal** ✅ *(Personal & Business)*:

**Scenarios**:
- Automatic backup of HA configuration to OneDrive (daily/weekly)
- Export of timer/reminder data to OneDrive
- File trigger: new file in OneDrive folder → HA action (e.g. doorbell camera image → auto-upload)

**Technical implementation**:
- Graph API: `/me/drive/root:/path:/children` for file upload
- Service `atc.backup_to_onedrive`: manual or automatic backup
- Webhook on OneDrive folder for file triggers

> ℹ️ **Note**: Personal accounts include 5 GB of free OneDrive storage. This is sufficient for configuration backups.

**SharePoint** 🏢 *(Business only)*:
- SharePoint file triggers and folder webhooks are exclusively available with Microsoft 365 Business/Work accounts.
- Personal Microsoft accounts do not have access to SharePoint resources.

### 15.5 Google Workspace – Extensions

**Google Tasks** ✅ *(Personal & Business)*:
- Bidirectional sync with HA ToDo platform (analogous to Microsoft To Do)
- Tasks as HA reminders, completion from HA

**Google Meet – Presence** ✅ *(Personal & Business, indirect via Google Calendar)*:
- Derive meeting status from active Google Calendar events
- `binary_sensor.atc_google_in_meeting_<name>` when event with Meet link is active

> ℹ️ **Note**: There is no direct Google Meet Presence API endpoint (for neither personal nor business accounts). Meeting status is derived solely from active Google Calendar events containing a Meet link – this works identically for all account types and is not a limitation compared to business accounts.

**Google Gmail – Email Triggers** ⚠️ *(Restricted for personal users)*:
- Gmail API (Pub/Sub Push) for email triggers
- Service `atc.send_gmail`: send email via Gmail API

> ⚠️ **Note for personal users**: The Gmail API requires a Google Cloud project with Pub/Sub enabled. Gmail scopes are classified by Google as "restricted" and require a thorough app verification process for a central app registration (security assessment, privacy policy, domain verification). For personal users with their own Client ID, usage is possible but will display a Google security warning at login (→ Open Question 15).

### 15.6 Apple Extensions

**Apple Reminders (via CalDAV extension)**:
- Partially accessible via CalDAV VTODO components
- Sync with HA ToDo platform

**iCloud Drive**:
- No official API – limited access via third-party libraries; not recommended for production use

### 15.7 Overview: Integration Roadmap

| Feature | Provider | Priority | Complexity | Phase | Account Type |
|---------|----------|----------|------------|-------|--------------|
| Bidirectional calendar sync | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | High | 3 | ✅ All |
| Calendar trigger (keyword) | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | Medium | 3 | ✅ All |
| Teams presence sensor | Microsoft | ⭐⭐⭐⭐ | Medium | 4 | 🏢 Business only |
| To Do sync | Microsoft | ⭐⭐⭐⭐ | Medium | 4 | ✅ Personal & Business |
| Tasks sync | Google | ⭐⭐⭐⭐ | Medium | 4 | ✅ Personal & Business |
| Email trigger (inbox) | Microsoft / Google | ⭐⭐⭐ | Medium | 4 | ✅ / ⚠️ (*) |
| Send email (service) | Microsoft / Google | ⭐⭐⭐ | Low | 4 | ✅ / ⚠️ (*) |
| OneDrive backup | Microsoft | ⭐⭐⭐ | Low | 4 | ✅ Personal (5 GB) & Business |
| Planner tasks | Microsoft | ⭐⭐ | Medium | 5 | 🏢 Business only |
| SharePoint file trigger | Microsoft | ⭐⭐ | High | 5 | 🏢 Business only |
| iCloud Drive | Apple | ⭐ | Very high | – | – (no official API) |

(*) Microsoft Outlook: ✅ Personal & Business. Google Gmail: ⚠️ Requires Google Cloud project + Pub/Sub; for a central app registration a Google app verification may be required.

---
