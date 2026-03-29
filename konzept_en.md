# Concept: HA Advanced Timer & Calendar

## 1. Overview & Goals

A custom component for Home Assistant covering the following core areas:

- **Timer / Scheduler**: Control entities (switches, lights, etc.) on a schedule
- **Reminder / Calendar**: Reminders, appointments, anniversaries, to-dos
- **Telegram Integration**: Notifications and bidirectional bot control (interactive when HA Telegram Bot is present)
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

Conditions block the timer trigger when not met:

- **Entity state**: e.g. `sensor.rain_sensor == 'raining'` → skip timer
- **Time window**: Only execute between 06:00–20:00
- **Numeric threshold**: e.g. `sensor.soil_moisture < 30`
- **Template**: Any HA template

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

## 5. Telegram Integration

### 5.1 Operating Modes

**Mode A – Standalone** (simple): Enter Bot Token + Chat ID directly in the Config Flow → the integration sends messages itself via the Telegram Bot API. Outbound notifications only, no inbound commands.

**Mode B – HA Telegram Bot** (advanced, recommended): Use the existing `telegram_bot` integration in HA. When present, **bidirectional and interactive** communication is enabled:
- Outbound: messages and inline keyboards via `notify.<telegram_service>`
- Inbound: commands and callback responses via HA events (`telegram_command`, `telegram_callback`)
- Interactive inline keyboards for confirmations, selections, and status queries

### 5.2 Notifications

Triggered when:

- Timer fires (start & end)
- Condition prevents execution ("Irrigation skipped – rain detected")
- Reminder/appointment coming up soon
- To-do due
- Error / timer disabled

Message format configurable (template-based), e.g.:

```
🌿 Irrigation Zone 1 started
Duration: 10 minutes | Next run: Tomorrow 06:00
```

### 5.3 Bot Control (Mode B – HA Telegram Bot)

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

## 6. HA Entities of the Integration

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

---

## 12. Phase Plan (Implementation Recommendation)

### Phase 1 – Core (MVP)
- HACS compliance (`hacs.json`, HACS-compliant structure)
- Persistence & storage (including migration engine)
- Multi-instance support via `config_entries`
- Scheduler engine (`daily`, `weekdays`, `interval`, `yearly`, `once`)
- Actions (`turn_on`, `turn_off`, duration)
- Conditions (entity state, template) – generic condition logic
- HA entities (switch, sensor)
- Config Flow (without Telegram, without external calendars)
- Calendar platform
- Services
- **Lovelace Custom Cards** (`atc-timer-card`, `atc-reminder-card`, `atc-status-card`)
- **ATC Dashboard** (automatically installed default dashboard)

### Phase 2 – Telegram & Reminder
- Telegram Mode A (standalone, outbound only)
- Telegram Mode B (HA integration, bidirectional & interactive via inline keyboards)
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
- Import/export
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

| Provider | Protocol / API | Authentication |
|----------|---------------|----------------|
| Microsoft 365 / Outlook | Microsoft Graph API (REST) | OAuth2 – Device Code Flow or Authorization Code Flow with PKCE |
| Google Calendar | Google Calendar API v3 (REST) | OAuth2 – Authorization Code Flow with PKCE |
| Apple iCloud Calendar | CalDAV (RFC 4791) | App-specific password (Apple ID + iCloud password alternative) |
| Exchange Server (On-Premise) | EWS (Exchange Web Services) or CalDAV | NTLM / Basic Auth / Modern Auth |

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

── Google Calendar ────────────────────────────────────────────
2. Enter display name
3. OAuth2 Authorization URL is generated:
   → HA opens an internal callback endpoint on port 8123
   → User opens URL in browser → signs in to Google → grants permissions
   → After redirect: token automatically saved
4. Calendar list → select → sync direction

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

---

## 15. Further Microsoft Office / Productivity Integrations

### 15.1 Microsoft Teams – Presence & Meeting Control

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

**Microsoft To Do**:
- REST API: read/write task lists (`/me/todo/lists/{listId}/tasks`)
- Bidirectional sync with HA ToDo platform
- Due tasks as HA reminders → notification via Telegram
- Create new tasks from HA (via HA dashboard or service)

**Microsoft Planner** (team tasks):
- Task status as HA sensor (e.g. project progress)
- Create new tasks on HA events (e.g. "Replace filter" when air quality sensor exceeds threshold)

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

**Scenarios**:
- Automatic backup of HA configuration to OneDrive (daily/weekly)
- Export of timer/reminder data to OneDrive
- File trigger: new file in OneDrive folder → HA action (e.g. doorbell camera image → auto-upload)

**Technical implementation**:
- Graph API: `/me/drive/root:/path:/children` for file upload
- Service `atc.backup_to_onedrive`: manual or automatic backup
- Webhook on OneDrive folder for file triggers

### 15.5 Google Workspace – Extensions

**Google Tasks**:
- Bidirectional sync with HA ToDo platform (analogous to Microsoft To Do)
- Tasks as HA reminders, completion from HA

**Google Meet – Presence** (via Google Calendar):
- Derive meeting status from active Google Calendar events
- `binary_sensor.atc_google_in_meeting_<name>` when event with Meet link is active

**Google Gmail – Email Triggers**:
- Gmail API (Pub/Sub Push) for email triggers
- Service `atc.send_gmail`: send email via Gmail API

### 15.6 Apple Extensions

**Apple Reminders (via CalDAV extension)**:
- Partially accessible via CalDAV VTODO components
- Sync with HA ToDo platform

**iCloud Drive**:
- No official API – limited access via third-party libraries; not recommended for production use

### 15.7 Overview: Integration Roadmap

| Feature | Provider | Priority | Complexity | Phase |
|---------|----------|----------|------------|-------|
| Bidirectional calendar sync | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | High | 3 |
| Calendar trigger (keyword) | Microsoft / Google / Apple | ⭐⭐⭐⭐⭐ | Medium | 3 |
| Teams presence sensor | Microsoft | ⭐⭐⭐⭐ | Medium | 4 |
| To Do / Tasks sync | Microsoft / Google | ⭐⭐⭐⭐ | Medium | 4 |
| Email trigger (inbox) | Microsoft / Google | ⭐⭐⭐ | Medium | 4 |
| Send email (service) | Microsoft / Google | ⭐⭐⭐ | Low | 4 |
| OneDrive backup | Microsoft | ⭐⭐⭐ | Low | 4 |
| Planner tasks | Microsoft | ⭐⭐ | Medium | 5 |
| SharePoint file trigger | Microsoft | ⭐⭐ | High | 5 |
| iCloud Drive | Apple | ⭐ | Very high | – |

---
