"""Service handlers for HA Advanced Timer & Calendar."""
from __future__ import annotations
import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    ScheduleType,
    IntervalUnit,
    ReminderType,
    SunEvent,
    SyncDirection,
    ConflictStrategy,
    SERVICE_CREATE_TIMER,
    SERVICE_UPDATE_TIMER,
    SERVICE_DELETE_TIMER,
    SERVICE_ENABLE_TIMER,
    SERVICE_DISABLE_TIMER,
    SERVICE_PAUSE_TIMER,
    SERVICE_SKIP_NEXT,
    SERVICE_RUN_NOW,
    SERVICE_CREATE_REMINDER,
    SERVICE_COMPLETE_TODO,
    SERVICE_SYNC_CALENDAR,
    SERVICE_ADD_CALENDAR_ACCOUNT,
    SERVICE_REMOVE_CALENDAR_ACCOUNT,
    SERVICE_CREATE_EXTERNAL_EVENT,
    SERVICE_DELETE_EXTERNAL_EVENT,
    SERVICE_CREATE_CALENDAR_TRIGGER,
    SERVICE_DELETE_CALENDAR_TRIGGER,
    TimerStatus,
)
from .storage import ATCStorage

_LOGGER = logging.getLogger(__name__)

_TIMER_ID_SCHEMA = vol.Schema({
    vol.Required("timer_id"): str,
})

_CREATE_TIMER_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Optional("enabled", default=True): bool,
    vol.Optional("schedule_type", default=ScheduleType.ONCE): vol.In(
        [s.value for s in ScheduleType]
    ),
    vol.Optional("time"): str,
    vol.Optional("weekdays"): [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))],
    vol.Optional("datetime"): str,
    vol.Optional("interval"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("interval_unit", default=IntervalUnit.DAYS): vol.In(
        [u.value for u in IntervalUnit]
    ),
    vol.Optional("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
    vol.Optional("cron"): str,
    vol.Optional("sun_event", default=SunEvent.SUNRISE): vol.In(
        [e.value for e in SunEvent]
    ),
    vol.Optional("sun_offset_minutes", default=0): vol.Coerce(int),
    vol.Optional("actions", default=[]): list,
    vol.Optional("conditions", default=[]): list,
    vol.Optional("notifications", default={}): dict,
}, extra=vol.ALLOW_EXTRA)

_UPDATE_TIMER_SCHEMA = vol.Schema({
    vol.Required("timer_id"): str,
    vol.Optional("name"): str,
    vol.Optional("enabled"): bool,
    vol.Optional("schedule_type"): vol.In([s.value for s in ScheduleType]),
    vol.Optional("time"): str,
    vol.Optional("weekdays"): list,
    vol.Optional("datetime"): str,
    vol.Optional("interval"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("interval_unit"): vol.In([u.value for u in IntervalUnit]),
    vol.Optional("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
    vol.Optional("cron"): str,
    vol.Optional("sun_event"): vol.In([e.value for e in SunEvent]),
    vol.Optional("sun_offset_minutes"): vol.Coerce(int),
    vol.Optional("actions"): list,
    vol.Optional("conditions"): list,
    vol.Optional("notifications"): dict,
}, extra=vol.ALLOW_EXTRA)

_CREATE_REMINDER_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Optional("type", default=ReminderType.REMINDER): vol.In(
        [r.value for r in ReminderType]
    ),
    vol.Optional("datetime"): str,
    vol.Optional("date"): str,
    vol.Optional("due_date"): str,
    vol.Optional("description", default=""): str,
    vol.Optional("completed", default=False): bool,
    vol.Optional("notifications", default={}): dict,
}, extra=vol.ALLOW_EXTRA)

_ADD_CALENDAR_ACCOUNT_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Required("provider"): vol.In(["microsoft", "google", "apple"]),
    vol.Optional("sync_direction", default=SyncDirection.BIDIRECTIONAL): vol.In(
        [d.value for d in SyncDirection]
    ),
    vol.Optional("conflict_strategy", default=ConflictStrategy.NEWEST_WINS): vol.In(
        [s.value for s in ConflictStrategy]
    ),
    vol.Optional("calendars", default=[]): list,
    vol.Optional("client_id", default=""): str,
    vol.Optional("client_secret", default=""): str,
    vol.Optional("tenant_id", default=""): str,
    vol.Optional("username", default=""): str,
    vol.Optional("password", default=""): str,
    vol.Optional("caldav_url", default=""): str,
}, extra=vol.ALLOW_EXTRA)

_CREATE_EXTERNAL_EVENT_SCHEMA = vol.Schema({
    vol.Required("account_id"): str,
    vol.Required("calendar_id"): str,
    vol.Required("summary"): str,
    vol.Optional("description", default=""): str,
    vol.Optional("start"): str,
    vol.Optional("end"): str,
    vol.Optional("location", default=""): str,
    vol.Optional("all_day", default=False): bool,
}, extra=vol.ALLOW_EXTRA)

_CREATE_CALENDAR_TRIGGER_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Required("account_id"): str,
    vol.Optional("calendar_id"): str,
    vol.Optional("keyword_filter"): str,
    vol.Optional("offset_minutes", default=0): vol.Coerce(int),
    vol.Optional("actions", default=[]): list,
}, extra=vol.ALLOW_EXTRA)


def _get_coordinator(hass: HomeAssistant):
    """Get the first available coordinator from hass.data."""
    domain_data = hass.data.get(DOMAIN, {})
    for entry_data in domain_data.values():
        if isinstance(entry_data, dict) and "coordinator" in entry_data:
            return entry_data["coordinator"]
    return None


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all ATC services."""

    async def handle_create_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        data = await coordinator.storage.async_load()
        timer: dict[str, Any] = {
            "id": ATCStorage.new_id(),
            "name": call.data["name"],
            "enabled": call.data.get("enabled", True),
            "schedule_type": call.data.get("schedule_type", ScheduleType.ONCE),
            "time": call.data.get("time"),
            "weekdays": call.data.get("weekdays", []),
            "datetime": call.data.get("datetime"),
            "interval": call.data.get("interval"),
            "interval_unit": call.data.get("interval_unit", IntervalUnit.DAYS),
            "month": call.data.get("month"),
            "day": call.data.get("day"),
            "cron": call.data.get("cron"),
            "sun_event": call.data.get("sun_event", SunEvent.SUNRISE),
            "sun_offset_minutes": call.data.get("sun_offset_minutes", 0),
            "actions": call.data.get("actions", []),
            "conditions": call.data.get("conditions", []),
            "notifications": call.data.get("notifications", {}),
            "status": TimerStatus.IDLE,
            "last_run": None,
            "next_run": None,
        }
        data.setdefault("timers", []).append(timer)
        await coordinator.storage.async_save(data)
        if timer["enabled"]:
            domain_data = hass.data.get(DOMAIN, {})
            for entry_data in domain_data.values():
                if isinstance(entry_data, dict) and "scheduler" in entry_data:
                    entry_data["scheduler"]._schedule_timer(timer)
        await coordinator.async_request_refresh()

    async def handle_update_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        data = await coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                update_fields = [
                    "name", "enabled", "schedule_type", "time", "weekdays",
                    "datetime", "interval", "interval_unit", "month", "day",
                    "cron", "sun_event", "sun_offset_minutes", "actions",
                    "conditions", "notifications",
                ]
                for field in update_fields:
                    if field in call.data:
                        timer[field] = call.data[field]
                break
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_delete_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        data = await coordinator.storage.async_load()
        data["timers"] = [t for t in data.get("timers", []) if t["id"] != timer_id]
        await coordinator.storage.async_save(data)
        domain_data = hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "scheduler" in entry_data:
                scheduler = entry_data["scheduler"]
                if timer_id in scheduler._cancel_callbacks:
                    scheduler._cancel_callbacks.pop(timer_id)()
        await coordinator.async_request_refresh()

    async def handle_enable_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        data = await coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["enabled"] = True
                break
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_disable_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        data = await coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["enabled"] = False
                break
        await coordinator.storage.async_save(data)
        domain_data = hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "scheduler" in entry_data:
                scheduler = entry_data["scheduler"]
                if timer_id in scheduler._cancel_callbacks:
                    scheduler._cancel_callbacks.pop(timer_id)()
        await coordinator.async_request_refresh()

    async def handle_pause_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        data = await coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["status"] = TimerStatus.PAUSED
                break
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_skip_next(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        data = await coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["status"] = TimerStatus.SKIPPED
                break
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_run_now(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        timer_id = call.data["timer_id"]
        domain_data = hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "scheduler" in entry_data:
                await entry_data["scheduler"]._fire_timer(timer_id)
                break

    async def handle_create_reminder(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        data = await coordinator.storage.async_load()
        reminder: dict[str, Any] = {
            "id": ATCStorage.new_id(),
            "name": call.data["name"],
            "type": call.data.get("type", ReminderType.REMINDER),
            "datetime": call.data.get("datetime"),
            "date": call.data.get("date"),
            "due_date": call.data.get("due_date"),
            "description": call.data.get("description", ""),
            "completed": call.data.get("completed", False),
            "notifications": call.data.get("notifications", {}),
        }
        data.setdefault("reminders", []).append(reminder)
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_complete_todo(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        reminder_id = call.data["reminder_id"]
        data = await coordinator.storage.async_load()
        for reminder in data.get("reminders", []):
            if reminder["id"] == reminder_id:
                reminder["completed"] = True
                break
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_sync_calendar(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        account_id = call.data.get("account_id")
        data = await coordinator.storage.async_load()
        try:
            from .external_calendars.sync_engine import ATCSyncEngine
            engine = ATCSyncEngine(hass, coordinator)
            await engine.async_sync(account_id)
        except Exception as exc:
            _LOGGER.error("Calendar sync error: %s", exc)
        await coordinator.async_request_refresh()

    async def handle_add_calendar_account(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        data = await coordinator.storage.async_load()
        account: dict[str, Any] = {
            "id": ATCStorage.new_id(),
            "name": call.data["name"],
            "provider": call.data["provider"],
            "sync_direction": call.data.get("sync_direction", SyncDirection.BIDIRECTIONAL),
            "conflict_strategy": call.data.get("conflict_strategy", ConflictStrategy.NEWEST_WINS),
            "calendars": call.data.get("calendars", []),
            "client_id": call.data.get("client_id", ""),
            "client_secret": call.data.get("client_secret", ""),
            "tenant_id": call.data.get("tenant_id", ""),
            "username": call.data.get("username", ""),
            "password": call.data.get("password", ""),
            "caldav_url": call.data.get("caldav_url", ""),
            "sync_status": "idle",
            "last_sync": None,
            "access_token": None,
            "refresh_token": None,
            "token_expiry": None,
        }
        data.setdefault("calendar_accounts", []).append(account)
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_remove_calendar_account(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        account_id = call.data["account_id"]
        data = await coordinator.storage.async_load()
        data["calendar_accounts"] = [
            a for a in data.get("calendar_accounts", []) if a["id"] != account_id
        ]
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_create_external_event(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        try:
            from .external_calendars.sync_engine import ATCSyncEngine
            engine = ATCSyncEngine(hass, coordinator)
            await engine.async_create_event(
                call.data["account_id"],
                call.data["calendar_id"],
                {
                    "summary": call.data["summary"],
                    "description": call.data.get("description", ""),
                    "start": call.data.get("start"),
                    "end": call.data.get("end"),
                    "location": call.data.get("location", ""),
                    "all_day": call.data.get("all_day", False),
                },
            )
        except Exception as exc:
            _LOGGER.error("Create external event error: %s", exc)
        await coordinator.async_request_refresh()

    async def handle_delete_external_event(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        try:
            from .external_calendars.sync_engine import ATCSyncEngine
            engine = ATCSyncEngine(hass, coordinator)
            await engine.async_delete_event(
                call.data["account_id"],
                call.data["calendar_id"],
                call.data["event_id"],
            )
        except Exception as exc:
            _LOGGER.error("Delete external event error: %s", exc)
        await coordinator.async_request_refresh()

    async def handle_create_calendar_trigger(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        data = await coordinator.storage.async_load()
        trigger: dict[str, Any] = {
            "id": ATCStorage.new_id(),
            "name": call.data["name"],
            "account_id": call.data["account_id"],
            "calendar_id": call.data.get("calendar_id"),
            "keyword_filter": call.data.get("keyword_filter"),
            "offset_minutes": call.data.get("offset_minutes", 0),
            "actions": call.data.get("actions", []),
            "enabled": True,
        }
        data.setdefault("calendar_triggers", []).append(trigger)
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    async def handle_delete_calendar_trigger(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            return
        trigger_id = call.data["trigger_id"]
        data = await coordinator.storage.async_load()
        data["calendar_triggers"] = [
            t for t in data.get("calendar_triggers", []) if t["id"] != trigger_id
        ]
        await coordinator.storage.async_save(data)
        await coordinator.async_request_refresh()

    # Register all services
    hass.services.async_register(DOMAIN, SERVICE_CREATE_TIMER, handle_create_timer, schema=_CREATE_TIMER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_TIMER, handle_update_timer, schema=_UPDATE_TIMER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_TIMER, handle_delete_timer, schema=_TIMER_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_TIMER, handle_enable_timer, schema=_TIMER_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISABLE_TIMER, handle_disable_timer, schema=_TIMER_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PAUSE_TIMER, handle_pause_timer, schema=_TIMER_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SKIP_NEXT, handle_skip_next, schema=_TIMER_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RUN_NOW, handle_run_now, schema=_TIMER_ID_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CREATE_REMINDER, handle_create_reminder, schema=_CREATE_REMINDER_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_COMPLETE_TODO, handle_complete_todo,
        schema=vol.Schema({vol.Required("reminder_id"): str})
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SYNC_CALENDAR, handle_sync_calendar,
        schema=vol.Schema({vol.Optional("account_id"): str})
    )
    hass.services.async_register(DOMAIN, SERVICE_ADD_CALENDAR_ACCOUNT, handle_add_calendar_account, schema=_ADD_CALENDAR_ACCOUNT_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_CALENDAR_ACCOUNT, handle_remove_calendar_account,
        schema=vol.Schema({vol.Required("account_id"): str})
    )
    hass.services.async_register(DOMAIN, SERVICE_CREATE_EXTERNAL_EVENT, handle_create_external_event, schema=_CREATE_EXTERNAL_EVENT_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_EXTERNAL_EVENT, handle_delete_external_event,
        schema=vol.Schema({
            vol.Required("account_id"): str,
            vol.Required("calendar_id"): str,
            vol.Required("event_id"): str,
        })
    )
    hass.services.async_register(DOMAIN, SERVICE_CREATE_CALENDAR_TRIGGER, handle_create_calendar_trigger, schema=_CREATE_CALENDAR_TRIGGER_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_CALENDAR_TRIGGER, handle_delete_calendar_trigger,
        schema=vol.Schema({vol.Required("trigger_id"): str})
    )
