# HA Advanced Timer & Calendar – Developer Guide

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Model](#2-data-model)
3. [Storage & Migration](#3-storage--migration)
4. [Scheduler Internals](#4-scheduler-internals)
5. [Adding a New Schedule Type](#5-adding-a-new-schedule-type)
6. [Notification System](#6-notification-system)
7. [External Calendar Providers](#7-external-calendar-providers)
8. [Testing Guidelines](#8-testing-guidelines)
9. [Contributing Guidelines](#9-contributing-guidelines)

---

## 1. Architecture Overview

```
custom_components/advanced_timer_calendar/
├── __init__.py                  # Entry setup, platform loading, service registration
├── const.py                     # All enumerations and constants
├── coordinator.py               # DataUpdateCoordinator – central state hub
├── storage.py                   # HA Store wrapper + schema migration
├── scheduler.py                 # Next-run calculation engine
├── config_flow.py               # UI config flow + options flow
├── options_flow.py              # Options (reconfigure) flow
├── services.py                  # Service handlers
├── services.yaml                # Service schema definitions
│
├── calendar.py                  # CalendarEntity platform
├── sensor.py                    # SensorEntity platform (next run, stats)
├── switch.py                    # SwitchEntity platform (enable/disable)
├── todo.py                      # TodoListEntity platform
│
├── notifications.py             # ATCNotificationManager
├── telegram_bot.py              # Telegram Mode B direct bot
├── voice_notifications.py       # Voice notification adapter
├── notification_escalation.py   # Escalation manager (Phase 4)
│
├── smart_watering.py            # Smart watering algorithm (Phase 4)
├── timer_templates.py           # Built-in timer templates (Phase 4)
├── import_export.py             # JSON import/export + YAML generation (Phase 4)
├── statistics.py                # Execution history and stats (Phase 4)
│
└── external_calendars/
    ├── __init__.py
    ├── base.py                  # AbstractCalendarProvider
    ├── microsoft.py             # Microsoft Graph API provider
    ├── google.py                # Google Calendar API provider
    └── apple.py                 # Apple CalDAV provider
```

### Request Flow

```
HA Event Bus / Cron
        │
        ▼
  scheduler.py  ──── calculates next_run ────►  coordinator.py
        │                                              │
        │ fires HA event                               │ stores state
        ▼                                              ▼
  services.py                                    storage.py
  (run_now, skip, etc.)                         (HA Store JSON)
        │
        ├──► notifications.py ──► Telegram / Voice
        ├──► smart_watering.py ──► adjusted duration
        └──► statistics.py ──► record_execution
```

The `ATCDataCoordinator` is the single source of truth. All platform entities subscribe to coordinator updates via `CoordinatorEntity`.

---

## 2. Data Model

All data is persisted in HA's `.storage/advanced_timer_calendar_<entry_id>` JSON file.

### Timer Object

```python
{
    "id": str,                          # UUID, auto-generated
    "name": str,                        # Display name
    "schedule_type": ScheduleType,      # "daily" | "weekdays" | "interval" | "cron" | "sun" | "once" | "yearly"
    "time": str,                        # "HH:MM:SS" (local time)
    "weekdays": list[int],              # [0..6], Mon=0; only for schedule_type=weekdays
    "interval_value": int,              # only for schedule_type=interval
    "interval_unit": IntervalUnit,      # "days" | "weeks" | "months"
    "cron_expression": str,             # only for schedule_type=cron
    "sun_event": SunEvent,              # "sunrise" | "sunset"
    "sun_offset_minutes": int,          # offset in minutes (negative=before)
    "yearly_month": int,                # 1..12, only for schedule_type=yearly
    "yearly_day": int,                  # 1..31
    "enabled": bool,
    "paused": bool,
    "skip_next": bool,
    "next_run": str | None,             # ISO UTC timestamp
    "last_run": str | None,
    "actions": list[ActionObject],
    "conditions": ConditionNode | None,
    "smart_watering": dict | None,      # WateringProfile dict, optional
    "template_id": str | None,          # source template if instantiated
    "tags": list[str],
    "created_at": str,
    "updated_at": str,
}
```

### ActionObject

```python
{
    "entity_id": str,
    "service": str,                     # e.g. "switch.turn_on"
    "service_data": dict,               # additional service data
    "delay_seconds": int,               # delay before this action
    "duration_seconds": int | None,     # auto-off after this many seconds
}
```

### ConditionNode

```python
# Group node
{
    "type": "group",
    "operator": "and" | "or",
    "conditions": list[ConditionNode],
}

# Item node
{
    "type": "item",
    "condition_type": "state" | "numeric_below" | "numeric_above" | "numeric_between" | "template",
    "entity_id": str,
    "value": Any,                       # state value or numeric threshold
    "min_value": float,                 # for numeric_between
    "max_value": float,                 # for numeric_between
    "template": str,                    # for template type
}
```

### Reminder Object

```python
{
    "id": str,
    "title": str,
    "type": ReminderType,               # "reminder" | "todo" | "anniversary" | "appointment"
    "due_date": str | None,             # "YYYY-MM-DD"
    "due_time": str | None,             # "HH:MM:SS"
    "reminder_minutes_before": int,
    "recurrence": str | None,           # iCal RRULE string
    "notes": str,
    "completed": bool,
    "completed_at": str | None,
    "escalation": dict | None,          # EscalationConfig dict
    "calendar_account_id": str | None,  # linked external calendar
    "external_event_id": str | None,
    "created_at": str,
    "updated_at": str,
}
```

### CalendarAccount Object

```python
{
    "id": str,
    "provider": str,                    # "microsoft" | "google" | "apple"
    "name": str,
    "client_id": str,
    "client_secret": str,
    "tenant_id": str | None,            # Microsoft only
    "username": str | None,             # Apple only
    "password": str | None,             # Apple only (app-specific)
    "sync_direction": SyncDirection,    # "bidirectional" | "inbound" | "outbound"
    "conflict_strategy": ConflictStrategy,
    "last_sync": str | None,
    "enabled": bool,
}
```

---

## 3. Storage & Migration

Storage is handled by `ATCStorage` in `storage.py`. It wraps `homeassistant.helpers.storage.Store`.

### Adding a Migration

1. Increment `STORAGE_VERSION` in `const.py`.
2. Add a migration method in `ATCStorage._migrate()`:

```python
async def _migrate(self, raw: dict) -> dict:
    version = raw.get("schema_version", 1)
    if version < 2:
        raw = await self._migrate_v1_to_v2(raw)
    if version < 3:
        raw = await self._migrate_v2_to_v3(raw)
    return raw

async def _migrate_v1_to_v2(self, data: dict) -> dict:
    # Example: add new field with default to all timers
    for timer in data.get("timers", []):
        timer.setdefault("tags", [])
    data["schema_version"] = 2
    return data
```

3. Update `EMPTY_DATA` with the new default structure.
4. Write a test in `tests/test_storage.py` verifying migration from each old version.

### New ID Generation

```python
@staticmethod
def new_id() -> str:
    return str(uuid.uuid4())
```

---

## 4. Scheduler Internals

`scheduler.py` is responsible for calculating `next_run` timestamps and firing timers.

### Next-Run Calculation

`calculate_next_run(timer: dict, now: datetime) -> datetime | None` works as follows:

| Schedule Type | Logic |
|---|---|
| `once` | Returns the configured date/time if still in the future, else `None` |
| `daily` | Next occurrence of `time` after `now` (same day if not yet passed, else tomorrow) |
| `weekdays` | Scans forward up to 7 days for the next matching weekday + time |
| `interval` | `last_run + interval`; if never run, uses creation time + interval |
| `cron` | Uses `croniter` to compute next occurrence after `now` |
| `sun` | Calls `homeassistant.helpers.sun.get_astral_event_next()` + offset |
| `yearly` | Constructs date from `yearly_month`/`yearly_day` in current or next year |

### Scheduler Loop

The scheduler registers a single HA `async_track_point_in_time` listener per timer. When a timer fires:

1. Conditions are evaluated.
2. If `skip_next` is set, record `skipped` and clear flag.
3. Smart watering calculates adjusted duration (if profile attached).
4. Actions are executed in sequence with optional delays.
5. `statistics.record_execution()` is called.
6. `next_run` is recalculated and the listener is re-registered.

---

## 5. Adding a New Schedule Type

1. Add the new value to `ScheduleType` in `const.py`:

```python
class ScheduleType(StrEnum):
    ...
    BIWEEKLY = "biweekly"
```

2. Implement next-run logic in `scheduler.py`:

```python
elif schedule_type == ScheduleType.BIWEEKLY:
    # Every two weeks from last_run or creation
    base = _parse_ts(timer.get("last_run")) or _parse_ts(timer["created_at"])
    delta = timedelta(weeks=2)
    next_dt = base + delta
    while next_dt <= now:
        next_dt += delta
    return next_dt
```

3. Add the type to `services.yaml` schema validation.

4. Update `config_flow.py` / `options_flow.py` to expose the new type in the UI.

5. Update `import_export.py` → `_build_trigger()` to generate correct YAML.

6. Add tests in `tests/test_scheduler.py`.

---

## 6. Notification System

`ATCNotificationManager` (`notifications.py`) is the central dispatcher.

### Channel Architecture

```
ATCNotificationManager.async_send(item, event, context)
    │
    ├── _render_template(event)          # Jinja2 via HA template engine
    │
    ├── if telegram_mode == MODE_A:
    │       hass.services.async_call("notify", service_name, {...})
    │
    ├── if telegram_mode == MODE_B:
    │       ATCTelegramBot.send_message(text)
    │
    └── if voice_provider != NONE:
            ATCVoiceNotifications.speak(text)
```

### Adding a New Notification Channel

1. Create a new class in an appropriate module (e.g. `pushover.py`).
2. Implement `async def send(self, message: str) -> None`.
3. Add the channel type to `TelegramMode` or a new enum.
4. Instantiate and register the channel in `__init__.py` setup.
5. Call it from `ATCNotificationManager.async_send()`.

### Template Variables

All notification templates receive these variables:

| Variable | Description |
|---|---|
| `name` | Timer or reminder name |
| `time_until` | Human-readable time until event |
| `reason` | Reason for skip/error (if applicable) |
| `timer_id` / `reminder_id` | Unique identifier |
| `next_run` | Next scheduled run (ISO string) |

---

## 7. External Calendar Providers

All providers extend `AbstractCalendarProvider` in `external_calendars/base.py`.

### AbstractCalendarProvider Interface

```python
class AbstractCalendarProvider(ABC):
    @abstractmethod
    async def async_authenticate(self) -> bool: ...

    @abstractmethod
    async def async_get_events(
        self, start: datetime, end: datetime
    ) -> list[CalendarEvent]: ...

    @abstractmethod
    async def async_create_event(self, event: CalendarEvent) -> str: ...

    @abstractmethod
    async def async_update_event(self, event_id: str, event: CalendarEvent) -> bool: ...

    @abstractmethod
    async def async_delete_event(self, event_id: str) -> bool: ...
```

### Implementing a New Provider

1. Create `external_calendars/my_provider.py`.
2. Subclass `AbstractCalendarProvider` and implement all abstract methods.
3. Register the provider in `external_calendars/__init__.py`:

```python
PROVIDERS: dict[str, type[AbstractCalendarProvider]] = {
    "microsoft": MicrosoftCalendarProvider,
    "google": GoogleCalendarProvider,
    "apple": AppleCalDAVProvider,
    "my_provider": MyProvider,          # add here
}
```

4. Add credentials fields to `services.yaml` under `add_calendar_account`.
5. Handle OAuth / token refresh in `async_authenticate()`.
6. Add an integration test in `tests/test_external_calendars.py` using a mock HTTP client.

---

## 8. Testing Guidelines

### Test Structure

```
tests/
├── conftest.py                  # Shared fixtures (hass, coordinator, storage mock)
├── test_scheduler.py            # Next-run calculations for every schedule type
├── test_storage.py              # Migration tests for each schema version
├── test_smart_watering.py       # Algorithm with mocked sensor states
├── test_timer_templates.py      # Template instantiation and overrides
├── test_import_export.py        # Round-trip JSON import/export
├── test_statistics.py           # History recording, capping, stats calculation
├── test_notification_escalation.py
└── test_external_calendars.py   # Provider tests with aiohttp mock
```

### Running Tests

```bash
pytest tests/ -v --cov=custom_components/advanced_timer_calendar
```

### Mocking HA

Use `pytest-homeassistant-custom-component`:

```python
from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_my_feature(hass):
    entry = MockConfigEntry(domain="advanced_timer_calendar", data={...})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ...
```

### Mocking Sensor States

```python
hass.states.async_set("sensor.temperature", "35.0", {"unit_of_measurement": "°C"})
```

### Testing Smart Watering

```python
from custom_components.advanced_timer_calendar.smart_watering import (
    SmartWateringAlgorithm, WateringProfile
)

async def test_skip_on_rain(hass):
    hass.states.async_set("weather.home", "rainy", {
        "forecast": [{"precipitation_probability": 80}]
    })
    algo = SmartWateringAlgorithm(hass)
    profile = WateringProfile(
        timer_id="t1",
        weather_entity="weather.home",
        rain_probability_threshold=0.6,
    )
    assert algo.calculate_duration(profile) == 0
```

---

## 9. Contributing Guidelines

### Setting Up a Dev Environment

```bash
git clone https://github.com/your-org/HA-Advanced-Timer-and-Calendar
cd HA-Advanced-Timer-and-Calendar
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_dev.txt
```

### Code Style

- **Python 3.12+** with `from __future__ import annotations`
- Follow [HA development guidelines](https://developers.home-assistant.io/docs/development_guidelines)
- Use `ruff` for linting: `ruff check custom_components/`
- Type annotations on all public methods
- Docstrings on all public classes and methods (one-line for simple methods)

### Commit Convention

```
feat: short description of feature
fix: short description of fix
docs: documentation changes
refactor: code restructuring without behaviour change
test: add or update tests
chore: maintenance tasks
```

### Pull Request Checklist

- [ ] Python syntax verified: `python3 -c "import ast; ast.parse(open('file.py').read())"`
- [ ] Tests added or updated for changed behaviour
- [ ] `STORAGE_VERSION` incremented and migration added if data model changed
- [ ] `services.yaml` updated if new service parameters added
- [ ] Documentation updated (`docs/user_guide.md`, `docs/user_guide_de.md`)
- [ ] No secrets or credentials committed
- [ ] `ruff check` passes with zero errors

### Reporting Issues

Include:
1. Home Assistant version
2. ATC version (from `manifest.json`)
3. Relevant log output (filter for `advanced_timer_calendar`)
4. Minimal reproducible configuration (anonymised)
