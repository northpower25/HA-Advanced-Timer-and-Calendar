"""Switch platform for ATC – one switch per timer."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    entities = [
        ATCTimerSwitch(coordinator, entry.entry_id, timer)
        for timer in data.get("timers", [])
    ]
    async_add_entities(entities)


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
