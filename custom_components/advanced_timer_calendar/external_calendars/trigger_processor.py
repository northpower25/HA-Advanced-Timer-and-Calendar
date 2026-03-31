"""Trigger processor for calendar-based automations."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class ATCTriggerProcessor:
    """Watches external calendar events and fires HA actions based on triggers."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._scheduled: dict[str, Any] = {}

    async def async_process_triggers(self) -> None:
        """Evaluate all calendar triggers against external events and schedule callbacks."""
        data = await self.coordinator.storage.async_load()
        triggers = data.get("calendar_triggers", [])
        external_events = data.get("external_events", [])

        now = dt_util.now()

        for trigger in triggers:
            if not trigger.get("enabled", True):
                continue
            trigger_id = trigger["id"]
            account_id = trigger.get("account_id", "")
            calendar_id = trigger.get("calendar_id")
            keyword = trigger.get("keyword_filter", "").lower()
            offset_minutes = trigger.get("offset_minutes", 0)
            actions = trigger.get("actions", [])

            for ext_event in external_events:
                if ext_event.get("account_id") != account_id:
                    continue
                if calendar_id and ext_event.get("calendar_id") != calendar_id:
                    continue
                if keyword and keyword not in (ext_event.get("summary") or "").lower():
                    continue

                start_str = ext_event.get("start")
                if not start_str:
                    continue

                try:
                    event_start = dt_util.parse_datetime(start_str)
                    if event_start is None:
                        continue
                except (ValueError, TypeError):
                    continue

                fire_time = event_start - timedelta(minutes=offset_minutes)
                schedule_key = f"{trigger_id}_{ext_event.get('uid', '')}"

                if schedule_key in self._scheduled:
                    continue

                if fire_time <= now:
                    continue

                _LOGGER.debug(
                    "Scheduling calendar trigger %s for event '%s' at %s",
                    trigger_id,
                    ext_event.get("summary"),
                    fire_time,
                )

                async def _fire(
                    _fire_time: datetime,
                    _actions: list[dict] = actions,
                    _event: dict = ext_event,
                    _key: str = schedule_key,
                ) -> None:
                    self._scheduled.pop(_key, None)
                    for action in _actions:
                        await self._execute_action(action, _event)

                from homeassistant.core import callback

                @callback
                def _cb(
                    ft: datetime,
                    f=_fire,
                ) -> None:
                    self.hass.async_create_task(f(ft))

                cancel = async_track_point_in_time(self.hass, _cb, fire_time)
                self._scheduled[schedule_key] = cancel

    def cancel_all(self) -> None:
        """Cancel all scheduled trigger callbacks."""
        for cancel in self._scheduled.values():
            try:
                cancel()
            except Exception:
                pass
        self._scheduled.clear()

    async def _execute_action(
        self, action: dict[str, Any], event: dict[str, Any]
    ) -> None:
        """Execute a trigger action, injecting calendar event context."""
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
                service_data = dict(action.get("service_data", {}))
                # Inject calendar event context into service data
                service_data.setdefault("variables", {}).update({
                    "event_summary": event.get("summary", ""),
                    "event_start": event.get("start", ""),
                    "event_end": event.get("end", ""),
                    "event_location": event.get("location", ""),
                })
                if service_domain and service_name:
                    await self.hass.services.async_call(
                        service_domain,
                        service_name,
                        service_data,
                        blocking=True,
                    )
            elif action_type == "notify":
                notify_service = action.get("notify_service", "notify.notify")
                message_template = action.get("message", "Calendar event: {{ event_summary }}")
                from homeassistant.helpers.template import Template
                tmpl = Template(message_template, self.hass)
                message = str(tmpl.async_render({
                    "event_summary": event.get("summary", ""),
                    "event_start": event.get("start", ""),
                    "event_location": event.get("location", ""),
                }))
                parts = notify_service.split(".", 1)
                svc_domain = parts[0] if len(parts) == 2 else "notify"
                svc_name = parts[1] if len(parts) == 2 else notify_service
                await self.hass.services.async_call(
                    svc_domain,
                    svc_name,
                    {"message": message, "title": event.get("summary", "ATC Trigger")},
                    blocking=False,
                )
        except Exception as exc:
            _LOGGER.error("Trigger action execution error: %s", exc)
