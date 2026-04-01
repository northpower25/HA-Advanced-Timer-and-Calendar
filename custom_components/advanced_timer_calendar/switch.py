"""Switch platform for ATC – one switch per timer."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ATCDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ATCDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = coordinator.data or {}
    known_ids: set[str] = set()
    entities = []
    for timer in data.get("timers", []):
        entities.append(ATCTimerSwitch(coordinator, entry.entry_id, timer))
        known_ids.add(timer["id"])
    async_add_entities(entities)

    @callback
    def _check_new_timers() -> None:
        """Add switch entities for timers created after initial setup."""
        current_data = coordinator.data or {}
        new_entities = []
        for timer in current_data.get("timers", []):
            if timer["id"] not in known_ids:
                known_ids.add(timer["id"])
                new_entities.append(ATCTimerSwitch(coordinator, entry.entry_id, timer))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_check_new_timers))


class ATCTimerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch representing an ATC timer's enabled state."""

    def __init__(
        self,
        coordinator: ATCDataCoordinator,
        entry_id: str,
        timer: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._timer_id = timer["id"]
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_switch_{self._timer_id}"
        self._attr_name = timer.get("name", f"Timer {self._timer_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                return {
                    "timer_id": self._timer_id,
                    "schedule_type": timer.get("schedule_type"),
                    "time": timer.get("time"),
                    "datetime": timer.get("datetime"),
                    "interval": timer.get("interval"),
                    "interval_unit": timer.get("interval_unit"),
                    "month": timer.get("month"),
                    "day": timer.get("day"),
                    "cron": timer.get("cron"),
                    "sun_event": timer.get("sun_event"),
                    "sun_offset_minutes": timer.get("sun_offset_minutes"),
                    "actions": timer.get("actions", []),
                    "conditions": timer.get("conditions", []),
                }
        return {"timer_id": self._timer_id}

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                return bool(timer.get("enabled", False))
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        data = await self.coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                timer["enabled"] = True
                break
        await self.coordinator.storage.async_save(data)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        data = await self.coordinator.storage.async_load()
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                timer["enabled"] = False
                break
        await self.coordinator.storage.async_save(data)
        await self.coordinator.async_request_refresh()
