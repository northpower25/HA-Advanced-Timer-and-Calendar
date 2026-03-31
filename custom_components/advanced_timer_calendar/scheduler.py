"""Scheduler for ATC – handles all timer scheduling and execution."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers import sun as sun_helper
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ScheduleType,
    SunEvent,
    IntervalUnit,
    TimerStatus,
    NotificationEvent,
)

_LOGGER = logging.getLogger(__name__)


class ATCScheduler:
    """Manages scheduling and execution of all ATC timers."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._cancel_callbacks: dict[str, Callable] = {}

    async def async_start(self) -> None:
        """Schedule all enabled timers on startup."""
        data = await self.coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer.get("enabled", False):
                self._schedule_timer(timer)

    def cancel_all(self) -> None:
        """Cancel all pending timer callbacks."""
        for cancel in self._cancel_callbacks.values():
            try:
                cancel()
            except Exception:
                pass
        self._cancel_callbacks.clear()

    def _schedule_timer(self, timer: dict[str, Any]) -> None:
        """Calculate next run and register callback for a timer."""
        timer_id = timer["id"]
        if timer_id in self._cancel_callbacks:
            self._cancel_callbacks.pop(timer_id)()

        now = dt_util.now()
        next_run = self._calc_next_run(timer, now)
        if next_run is None:
            _LOGGER.debug("Timer %s has no future run time, not scheduling.", timer_id)
            return

        _LOGGER.debug("Scheduling timer %s for %s", timer_id, next_run)

        @callback
        def _fire_callback(fired_time: datetime) -> None:
            self.hass.async_create_task(self._fire_timer(timer_id))

        cancel = async_track_point_in_time(self.hass, _fire_callback, next_run)
        self._cancel_callbacks[timer_id] = cancel

    def _calc_next_run(self, timer: dict[str, Any], now: datetime) -> datetime | None:
        """Compute the next trigger time for any schedule type."""
        schedule_type = timer.get("schedule_type", ScheduleType.ONCE)
        tz = dt_util.get_time_zone(self.hass.config.time_zone or "UTC")

        if schedule_type == ScheduleType.ONCE:
            dt_str = timer.get("datetime")
            if not dt_str:
                return None
            try:
                run_dt = dt_util.parse_datetime(dt_str)
                if run_dt is None:
                    return None
                if run_dt.tzinfo is None:
                    run_dt = dt_util.as_local(run_dt)
                return run_dt if run_dt > now else None
            except (ValueError, TypeError):
                return None

        elif schedule_type == ScheduleType.DAILY:
            time_str = timer.get("time", "08:00")
            return self._next_daily(time_str, now, tz)

        elif schedule_type == ScheduleType.WEEKDAYS:
            time_str = timer.get("time", "08:00")
            weekdays = timer.get("weekdays", [])
            return self._next_weekday(time_str, weekdays, now, tz)

        elif schedule_type == ScheduleType.INTERVAL:
            interval = timer.get("interval", 1)
            unit = timer.get("interval_unit", IntervalUnit.DAYS)
            last_run_str = timer.get("last_run")
            return self._next_interval(interval, unit, last_run_str, now, tz)

        elif schedule_type == ScheduleType.YEARLY:
            month = timer.get("month", 1)
            day = timer.get("day", 1)
            time_str = timer.get("time", "08:00")
            return self._next_yearly(month, day, time_str, now, tz)

        elif schedule_type == ScheduleType.CRON:
            cron_expr = timer.get("cron", "0 8 * * *")
            return self._next_cron(cron_expr, now, tz)

        elif schedule_type == ScheduleType.SUN:
            event = timer.get("sun_event", SunEvent.SUNRISE)
            offset_minutes = timer.get("sun_offset_minutes", 0)
            return self._next_sun_event(event, offset_minutes, now)

        return None

    def _next_daily(self, time_str: str, now: datetime, tz) -> datetime | None:
        """Next daily occurrence of time_str."""
        try:
            h, m = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            return None
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def _next_weekday(
        self, time_str: str, weekdays: list[int], now: datetime, tz
    ) -> datetime | None:
        """Next occurrence on given weekdays (0=Mon … 6=Sun)."""
        if not weekdays:
            return None
        try:
            h, m = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            return None
        for delta in range(8):
            candidate = (now + timedelta(days=delta)).replace(
                hour=h, minute=m, second=0, microsecond=0
            )
            if candidate > now and candidate.weekday() in weekdays:
                return candidate
        return None

    def _next_interval(
        self,
        interval: int,
        unit: str,
        last_run_str: str | None,
        now: datetime,
        tz,
    ) -> datetime | None:
        """Next interval-based occurrence."""
        if last_run_str:
            try:
                last_run = dt_util.parse_datetime(last_run_str)
                if last_run and last_run.tzinfo is None:
                    last_run = dt_util.as_local(last_run)
            except (ValueError, TypeError):
                last_run = now
        else:
            last_run = now

        if unit == IntervalUnit.DAYS:
            delta = timedelta(days=interval)
        elif unit == IntervalUnit.WEEKS:
            delta = timedelta(weeks=interval)
        elif unit == IntervalUnit.MONTHS:
            delta = timedelta(days=interval * 30)
        else:
            delta = timedelta(days=interval)

        next_run = last_run + delta
        while next_run <= now:
            next_run += delta
        return next_run

    def _next_yearly(
        self, month: int, day: int, time_str: str, now: datetime, tz
    ) -> datetime | None:
        """Next yearly occurrence."""
        try:
            h, m = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            return None
        year = now.year
        try:
            candidate = now.replace(
                year=year, month=month, day=day, hour=h, minute=m, second=0, microsecond=0
            )
        except ValueError:
            return None
        if candidate <= now:
            try:
                candidate = candidate.replace(year=year + 1)
            except ValueError:
                return None
        return candidate

    def _next_cron(self, cron_expr: str, now: datetime, tz) -> datetime | None:
        """Simple cron expression parser (min hour dom month dow)."""
        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                return None
            minute_field, hour_field, dom_field, month_field, dow_field = parts

            def parse_field(field: str, min_val: int, max_val: int) -> list[int]:
                if field == "*":
                    return list(range(min_val, max_val + 1))
                values: set[int] = set()
                for part in field.split(","):
                    if "/" in part:
                        range_part, step_str = part.split("/", 1)
                        step = int(step_str)
                        if range_part == "*":
                            start, end = min_val, max_val
                        elif "-" in range_part:
                            s, e = range_part.split("-")
                            start, end = int(s), int(e)
                        else:
                            start = int(range_part)
                            end = max_val
                        values.update(range(start, end + 1, step))
                    elif "-" in part:
                        s, e = part.split("-")
                        values.update(range(int(s), int(e) + 1))
                    else:
                        values.add(int(part))
                return sorted(v for v in values if min_val <= v <= max_val)

            minutes = parse_field(minute_field, 0, 59)
            hours = parse_field(hour_field, 0, 23)
            doms = parse_field(dom_field, 1, 31)
            months = parse_field(month_field, 1, 12)
            dows = parse_field(dow_field, 0, 6)

            candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            for _ in range(366 * 24 * 60):
                if (
                    candidate.month in months
                    and candidate.day in doms
                    and candidate.weekday() in dows
                    and candidate.hour in hours
                    and candidate.minute in minutes
                ):
                    return candidate
                candidate += timedelta(minutes=1)
        except Exception as exc:
            _LOGGER.warning("Cron parse error for '%s': %s", cron_expr, exc)
        return None

    def _next_sun_event(
        self, event: str, offset_minutes: int, now: datetime
    ) -> datetime | None:
        """Next sunrise or sunset with optional offset."""
        try:
            event_name = "sunrise" if event == SunEvent.SUNRISE else "sunset"
            next_event = sun_helper.get_astral_event_next(
                self.hass, event_name, utc_point_in_time=dt_util.utcnow()
            )
            if next_event is None:
                return None
            return dt_util.as_local(next_event) + timedelta(minutes=offset_minutes)
        except Exception as exc:
            _LOGGER.warning("Sun event error: %s", exc)
            return None

    async def _fire_timer(self, timer_id: str) -> None:
        """Load timer, check conditions, execute actions, reschedule."""
        data = await self.coordinator.storage.async_load()
        timer = next((t for t in data.get("timers", []) if t["id"] == timer_id), None)
        if timer is None or not timer.get("enabled", False):
            return

        now = dt_util.now()
        conditions = timer.get("conditions", [])
        if conditions and not self._eval_conditions(conditions, now):
            _LOGGER.debug("Timer %s conditions not met – skipping.", timer_id)
            await self._update_timer_status(timer_id, TimerStatus.SKIPPED, data)
            await self._notify(timer, NotificationEvent.SKIPPED, {"reason": "conditions not met"})
            self._schedule_timer(timer)
            return

        _LOGGER.info("Firing timer %s", timer_id)
        await self._update_timer_status(timer_id, TimerStatus.RUNNING, data)
        await self._notify(timer, NotificationEvent.AFTER, {})

        for action in timer.get("actions", []):
            await self._execute_action(action)

        await self._update_timer_status(timer_id, TimerStatus.IDLE, data)
        await self._record_last_run(timer_id, now, data)
        await self._notify(timer, NotificationEvent.RESET, {})

        # Reload timer from storage (may have been updated during execution)
        data = await self.coordinator.storage.async_load()
        timer = next((t for t in data.get("timers", []) if t["id"] == timer_id), None)
        if timer and timer.get("enabled", False):
            if timer.get("schedule_type") == ScheduleType.ONCE:
                await self._set_timer_enabled(timer_id, False, data)
            else:
                self._schedule_timer(timer)

        await self.coordinator.async_request_refresh()

    def _eval_conditions(self, conditions: list[dict], now: datetime) -> bool:
        """Evaluate AND/OR condition tree."""
        if not conditions:
            return True
        logic = conditions[0].get("logic", "and") if conditions else "and"
        if logic == "or":
            return any(self._eval_condition_item(c) for c in conditions)
        return all(self._eval_condition_item(c) for c in conditions)

    def _eval_condition_item(self, item: dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        condition_type = item.get("type", "state")
        try:
            if condition_type == "state":
                entity_id = item.get("entity_id", "")
                expected = item.get("state", "")
                state = self.hass.states.get(entity_id)
                if state is None:
                    return False
                return state.state == expected

            elif condition_type == "numeric_state":
                entity_id = item.get("entity_id", "")
                above = item.get("above")
                below = item.get("below")
                state = self.hass.states.get(entity_id)
                if state is None:
                    return False
                try:
                    val = float(state.state)
                except (ValueError, TypeError):
                    return False
                if above is not None and val <= float(above):
                    return False
                if below is not None and val >= float(below):
                    return False
                return True

            elif condition_type == "template":
                template_str = item.get("template", "")
                from homeassistant.helpers.template import Template
                tmpl = Template(template_str, self.hass)
                result = tmpl.async_render()
                return str(result).lower() in ("true", "1", "yes")

        except Exception as exc:
            _LOGGER.warning("Condition eval error: %s", exc)
        return False

    async def _execute_action(self, action: dict[str, Any]) -> None:
        """Execute a single action with optional delay and duration."""
        delay = action.get("delay_seconds", 0)
        if delay and delay > 0:
            await asyncio.sleep(delay)

        action_type = action.get("action", "turn_on")
        entity_id = action.get("entity_id", "")

        try:
            if action_type in ("turn_on", "turn_off", "toggle"):
                domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
                await self.hass.services.async_call(
                    domain,
                    action_type,
                    {"entity_id": entity_id},
                    blocking=True,
                )
            elif action_type == "service":
                service_domain = action.get("service_domain", "")
                service_name = action.get("service_name", "")
                service_data = action.get("service_data", {})
                if service_domain and service_name:
                    await self.hass.services.async_call(
                        service_domain,
                        service_name,
                        service_data,
                        blocking=True,
                    )
        except Exception as exc:
            _LOGGER.error("Action execution error for %s: %s", action_type, exc)

        duration = action.get("duration_seconds", 0)
        if duration and duration > 0 and action_type == "turn_on":
            await asyncio.sleep(duration)
            try:
                domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
                await self.hass.services.async_call(
                    domain,
                    "turn_off",
                    {"entity_id": entity_id},
                    blocking=True,
                )
            except Exception as exc:
                _LOGGER.error("Duration turn_off error: %s", exc)

    async def _notify(
        self, timer: dict[str, Any], event: str, context: dict[str, Any]
    ) -> None:
        """Dispatch notifications for a timer event."""
        try:
            from .notifications import ATCNotificationManager
            mgr = ATCNotificationManager(self.hass)
            await mgr.async_send(timer, event, context)
        except Exception as exc:
            _LOGGER.warning("Notification dispatch error: %s", exc)

    async def _update_timer_status(
        self, timer_id: str, status: str, data: dict[str, Any]
    ) -> None:
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["status"] = status
                break
        await self.coordinator.storage.async_save(data)

    async def _record_last_run(
        self, timer_id: str, now: datetime, data: dict[str, Any]
    ) -> None:
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["last_run"] = now.isoformat()
                break
        await self.coordinator.storage.async_save(data)

    async def _set_timer_enabled(
        self, timer_id: str, enabled: bool, data: dict[str, Any]
    ) -> None:
        for timer in data.get("timers", []):
            if timer["id"] == timer_id:
                timer["enabled"] = enabled
                break
        await self.coordinator.storage.async_save(data)
