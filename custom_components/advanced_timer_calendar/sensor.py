"""Sensor platform for ATC – next run, last run, status per timer."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
    known_timer_ids: set[str] = set()
    known_account_ids: set[str] = set()
    entities: list[SensorEntity] = []
    for timer in data.get("timers", []):
        entities.append(ATCNextRunSensor(coordinator, entry.entry_id, timer))
        entities.append(ATCLastRunSensor(coordinator, entry.entry_id, timer))
        entities.append(ATCStatusSensor(coordinator, entry.entry_id, timer))
        known_timer_ids.add(timer["id"])
    for account in data.get("calendar_accounts", []):
        entities.append(ATCSyncStatusSensor(coordinator, entry.entry_id, account))
        known_account_ids.add(account["id"])
    async_add_entities(entities)

    @callback
    def _check_new_entities() -> None:
        """Add sensor entities for timers/accounts created after initial setup.

        Also removes stale sync sensor entities for accounts that have been deleted
        so the status card no longer shows them.
        """
        current_data = coordinator.data or {}
        new_entities: list[SensorEntity] = []
        for timer in current_data.get("timers", []):
            if timer["id"] not in known_timer_ids:
                known_timer_ids.add(timer["id"])
                new_entities.append(ATCNextRunSensor(coordinator, entry.entry_id, timer))
                new_entities.append(ATCLastRunSensor(coordinator, entry.entry_id, timer))
                new_entities.append(ATCStatusSensor(coordinator, entry.entry_id, timer))
        current_account_ids = {a["id"] for a in current_data.get("calendar_accounts", [])}
        for account in current_data.get("calendar_accounts", []):
            if account["id"] not in known_account_ids:
                known_account_ids.add(account["id"])
                new_entities.append(ATCSyncStatusSensor(coordinator, entry.entry_id, account))
        if new_entities:
            async_add_entities(new_entities)
        # Remove stale sync sensor entities for deleted accounts
        removed_account_ids = known_account_ids - current_account_ids
        if removed_account_ids:
            entity_reg = er.async_get(hass)
            for removed_id in removed_account_ids:
                unique_id = f"{entry.entry_id}_sensor_sync_{removed_id}"
                entity_id = entity_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
                if entity_id:
                    entity_reg.async_remove(entity_id)
            known_account_ids.difference_update(removed_account_ids)

    entry.async_on_unload(coordinator.async_add_listener(_check_new_entities))


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
    def available(self) -> bool:
        data = self.coordinator.data or {}
        return any(
            a["id"] == self._account_id
            for a in data.get("calendar_accounts", [])
        )

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        for account in data.get("calendar_accounts", []):
            if account["id"] == self._account_id:
                return account.get("sync_status", "idle")
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        for account in data.get("calendar_accounts", []):
            if account["id"] == self._account_id:
                return {
                    "account_id": self._account_id,
                    "provider": account.get("provider", ""),
                }
        return {"account_id": self._account_id}
