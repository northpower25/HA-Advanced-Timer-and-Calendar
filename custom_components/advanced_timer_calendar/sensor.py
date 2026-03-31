"""Sensor platform for ATC – next run, last run, status per timer."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import ATCDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ATCDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = coordinator.data or {}
    entities: list[SensorEntity] = []
    for timer in data.get("timers", []):
        entities.append(ATCNextRunSensor(coordinator, entry.entry_id, timer))
        entities.append(ATCLastRunSensor(coordinator, entry.entry_id, timer))
        entities.append(ATCStatusSensor(coordinator, entry.entry_id, timer))
    for account in data.get("calendar_accounts", []):
        entities.append(ATCSyncStatusSensor(coordinator, entry.entry_id, account))
    async_add_entities(entities)


class ATCNextRunSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing next scheduled run time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: ATCDataCoordinator,
        entry_id: str,
        timer: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._timer_id = timer["id"]
        self._attr_unique_id = f"{entry_id}_sensor_{self._timer_id}_next_run"
        self._attr_name = f"{timer.get('name', 'Timer')} Next Run"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                val = timer.get("next_run")
                if val:
                    return dt_util.parse_datetime(val)
        return None


class ATCLastRunSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing last run time."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: ATCDataCoordinator,
        entry_id: str,
        timer: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._timer_id = timer["id"]
        self._attr_unique_id = f"{entry_id}_sensor_{self._timer_id}_last_run"
        self._attr_name = f"{timer.get('name', 'Timer')} Last Run"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                val = timer.get("last_run")
                if val:
                    return dt_util.parse_datetime(val)
        return None


class ATCStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing timer status."""

    def __init__(
        self,
        coordinator: ATCDataCoordinator,
        entry_id: str,
        timer: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._timer_id = timer["id"]
        self._attr_unique_id = f"{entry_id}_sensor_{self._timer_id}_status"
        self._attr_name = f"{timer.get('name', 'Timer')} Status"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        for timer in data.get("timers", []):
            if timer["id"] == self._timer_id:
                return timer.get("status", "idle")
        return "idle"


class ATCSyncStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing external calendar sync status."""

    def __init__(
        self,
        coordinator: ATCDataCoordinator,
        entry_id: str,
        account: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._account_id = account["id"]
        self._attr_unique_id = f"{entry_id}_sensor_sync_{self._account_id}"
        self._attr_name = f"ATC Sync {account.get('name', self._account_id)}"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        for account in data.get("calendar_accounts", []):
            if account["id"] == self._account_id:
                return account.get("sync_status", "idle")
        return "idle"
