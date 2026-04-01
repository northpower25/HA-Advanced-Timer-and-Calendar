"""Calendar platform for ATC – 4 calendar entities."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, ReminderType
from .coordinator import ATCDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ATCDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        ATCAppointmentsCalendar(coordinator, entry.entry_id),
        ATCAnniversariesCalendar(coordinator, entry.entry_id),
        ATCTodosCalendar(coordinator, entry.entry_id),
        ATCTimerScheduleCalendar(coordinator, entry.entry_id),
    ])


class _ATCBaseCalendar(CoordinatorEntity, CalendarEntity):
    def __init__(
        self,
        coordinator: ATCDataCoordinator,
        entry_id: str,
        suffix: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_calendar_{suffix}"
        self._attr_name = name

    @property
    def event(self) -> CalendarEvent | None:
        events = self._get_upcoming_events()
        return events[0] if events else None

    def _get_upcoming_events(self) -> list[CalendarEvent]:
        return []

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return []


class ATCAppointmentsCalendar(_ATCBaseCalendar):
    """Calendar showing appointment reminders."""

    def __init__(self, coordinator: ATCDataCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "appointments", "ATC Appointments")

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        events = []
        for reminder in data.get("reminders", []):
            if reminder.get("type") != ReminderType.APPOINTMENT:
                continue
            dt_str = reminder.get("datetime") or reminder.get("date")
            if not dt_str:
                continue
            try:
                start = dt_util.parse_datetime(dt_str)
                if start is None:
                    start = dt_util.as_local(datetime.fromisoformat(dt_str))
                if start is not None:
                    if start.tzinfo is None:
                        start = dt_util.as_local(start)
                    if start_date <= start <= end_date:
                        events.append(CalendarEvent(
                            start=start,
                            end=start,
                            summary=reminder.get("name", "Appointment"),
                            description=reminder.get("description", ""),
                        ))
            except (ValueError, TypeError):
                pass
        return events


class ATCAnniversariesCalendar(_ATCBaseCalendar):
    """Calendar showing anniversary reminders."""

    def __init__(self, coordinator: ATCDataCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "anniversaries", "ATC Anniversaries")

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        events = []
        for reminder in data.get("reminders", []):
            if reminder.get("type") != ReminderType.ANNIVERSARY:
                continue
            dt_str = reminder.get("datetime") or reminder.get("date")
            if not dt_str:
                continue
            try:
                base = dt_util.parse_datetime(dt_str)
                if base is None:
                    base = dt_util.as_local(datetime.fromisoformat(dt_str))
                if base is None:
                    continue
                if base.tzinfo is None:
                    base = dt_util.as_local(base)
                for year_offset in range(-1, 3):
                    try:
                        candidate = base.replace(year=base.year + year_offset)
                        if start_date <= candidate <= end_date:
                            events.append(CalendarEvent(
                                start=candidate,
                                end=candidate,
                                summary=reminder.get("name", "Anniversary"),
                                description=reminder.get("description", ""),
                            ))
                    except ValueError:
                        pass
            except (ValueError, TypeError):
                pass
        return events


class ATCTodosCalendar(_ATCBaseCalendar):
    """Calendar showing todo reminders with due dates."""

    def __init__(self, coordinator: ATCDataCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "todos", "ATC Todos")

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        events = []
        for reminder in data.get("reminders", []):
            if reminder.get("type") != ReminderType.TODO:
                continue
            dt_str = reminder.get("due_date") or reminder.get("datetime")
            if not dt_str:
                continue
            try:
                due = dt_util.parse_datetime(dt_str)
                if due is None:
                    due = dt_util.as_local(datetime.fromisoformat(dt_str))
                if due is not None:
                    if due.tzinfo is None:
                        due = dt_util.as_local(due)
                    if start_date <= due <= end_date:
                        events.append(CalendarEvent(
                            start=due,
                            end=due,
                            summary=reminder.get("name", "Todo"),
                            description=reminder.get("description", ""),
                        ))
            except (ValueError, TypeError):
                pass
        return events


class ATCTimerScheduleCalendar(_ATCBaseCalendar):
    """Calendar showing timer scheduled runs."""

    def __init__(self, coordinator: ATCDataCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "timer_schedule", "ATC Timer Schedule")

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        data = self.coordinator.data or {}
        events = []
        for timer in data.get("timers", []):
            if not timer.get("enabled", False):
                continue
            next_run_str = timer.get("next_run")
            if not next_run_str:
                continue
            try:
                next_run = dt_util.parse_datetime(next_run_str)
                if next_run is not None:
                    if next_run.tzinfo is None:
                        next_run = dt_util.as_local(next_run)
                    if start_date <= next_run <= end_date:
                        events.append(CalendarEvent(
                            start=next_run,
                            end=next_run,
                            summary=f"\u23f0 {timer.get('name', 'Timer')}",
                            description=f"Scheduled timer run for {timer.get('name', 'Timer')}",
                        ))
            except (ValueError, TypeError):
                pass
        return events
