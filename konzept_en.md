# Concept: HA Advanced Timer & Calendar

## 1. Overview & Goals

A custom component for Home Assistant covering the following core areas:

- **Timer / Scheduler**: Control entities (switches, lights, etc.) on a schedule
- **Reminder / Calendar**: Reminders, appointments, anniversaries, to-dos
- **Telegram Integration**: Notifications and bot control
- **Persistence**: All data survives HA restarts
- **User-Friendliness**: Full configuration via the HA UI (Config Flow + Options Flow)

---

## 2. Architecture

### 2.1 Component Structure

```
custom_components/advanced_timer_calendar/
├── __init__.py              # Setup, Coordinator startup
├── manifest.json            # Metadata, dependencies
├── config_flow.py           # Setup wizard (UI)
├── options_flow.py          # Post-setup settings
├── const.py                 # Constants, enums
├── coordinator.py           # Central DataUpdateCoordinator
├── storage.py               # Persistence via HA Storage API
├── scheduler.py             # Timer logic & scheduling engine
├── calendar.py              # Calendar platform (CalendarEntity)
├── sensor.py                # Sensor platform (status, next trigger)
├── switch.py                # Switch platform (timer on/off)
├── services.yaml            # HA service definitions
├── services.py              # Service handlers
├── telegram_bot.py          # Telegram notification & control module
├── translations/
│   ├── de.json
│   └── en.json
└── strings.json
```

### 2.2 Data Storage

**HA Storage API** (`.storage/advanced_timer_calendar`) – JSON file written on every change. No data loss on restart.

Data structure (simplified):

```json
{
  "version": 1,
  "timers": [ { "...Timer object..." } ],
  "reminders": [ { "...Reminder object..." } ],
  "settings": { "...global settings..." }
}
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

**Mode A – Standalone** (simple): Enter Bot Token + Chat ID directly in the Config Flow → the integration sends messages itself via the Telegram Bot API.

**Mode B – HA Telegram Bot** (advanced): Use the existing `telegram_bot` integration in HA as a notification service.

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

### 5.3 Bot Control (Mode B)

Control timers via Telegram commands:

| Command | Function |
|---------|---------|
| `/timer list` | Show all timers |
| `/timer pause Garden` | Pause timer |
| `/timer resume Garden` | Resume timer |
| `/timer next Garden` | Show next run |
| `/reminder list` | Upcoming reminders |
| `/reminder add ...` | Quick-create reminder |
| `/status` | System overview |

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

---

## 8. Config Flow (Setup Wizard)

### Step 1 – General
- Name of the integration instance

### Step 2 – Telegram (optional)
- Mode: "No Telegram", "Own Bot", "HA Telegram Bot"
- For "Own Bot": Bot Token, Chat ID, send test message
- For "HA Telegram Bot": Select existing notification service

### Step 3 – Default Settings
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

### 9.2 Lovelace Cards (Phase 2, optional)
For maximum user-friendliness, custom cards could be developed:

- **ATC Timer Card**: Overview of all timers, quick on/off, next run
- **ATC Reminder Card**: Calendar view of upcoming appointments
- **ATC Quick Reminder Card**: Quickly create reminders

---

## 10. Technical Decisions & Open Questions

### Open Questions / Decision Required

1. **Minimum HA version**: Which HA version should be the minimum? Recommendation: 2023.9+ (stable Calendar & ToDo API)
2. **Multiple instances**: Should the integration be installable multiple times (e.g. "Garden", "House")? Or one central instance with groups/tags?
3. **Dependencies**: Use `croniter` (PyPI) for cron expressions and `python-telegram-bot` for standalone mode – or use only HA-internal tools?
4. **Migration strategy**: How should Storage schema migration work on updates (versioning in the storage file)?
5. **Telegram Bot Commands**: Should the bot be interactive (inline keyboards for confirmations) or just simple text commands?
6. **Irrigation sensor logic**: Should there be a dedicated "irrigation profile" feature, or is the generic condition logic sufficient?
7. **Lovelace Cards**: Include in Phase 1 or defer to Phase 2? Significantly increases complexity.
8. **HACS compatibility**: Develop HACS-compliant from the start (recommended) – requires a specific `hacs.json` file.

### Recommended Design Decisions

- **Storage over SQLite**: HA Storage API is the idiomatic solution – no custom database schema
- **DataUpdateCoordinator**: Central state management, all platforms subscribe to it
- **Native asyncio**: No blocking calls, everything async
- **HACS from the start**: Enables easy distribution and updates for non-technical users

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
- Persistence & storage
- Scheduler engine (`daily`, `weekdays`, `interval`, `yearly`, `once`)
- Actions (`turn_on`, `turn_off`, duration)
- Conditions (entity state, template)
- HA entities (switch, sensor)
- Config Flow (without Telegram)
- Calendar platform
- Services

### Phase 2 – Telegram & Reminder
- Telegram Mode A (standalone)
- Telegram Mode B (HA integration)
- Reminder/calendar types (anniversaries, to-dos)
- HA To-Do platform integration
- Sunrise/sunset trigger

### Phase 3 – Convenience & Extensions
- Lovelace cards
- Smart watering algorithm
- Timer templates
- Import/export
- Bot inline keyboards
- Statistics

---

## 13. Open Points for Clarification

Before starting implementation, please decide on the following:

1. **Which minimum HA version** should be supported?
2. **Should external Python libraries** (`croniter`, `python-telegram-bot`) be used, or should the integration avoid external dependencies?
3. **Cron expressions** desired for advanced users, or are the defined schedule types sufficient?
4. **Multi-instance support** (`config_entries`) from the start, or single instance?
5. **Confirm Phase 1 scope**: Is the MVP sensibly scoped, or should certain features be moved forward/back?
6. **Telegram priority**: Should Telegram already be included in Phase 1 (as it is a core requirement)?
7. **UI text language**: German and English from the start (`translations/de.json` + `en.json`)?
