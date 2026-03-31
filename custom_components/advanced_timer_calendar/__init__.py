"""HA Advanced Timer & Calendar integration."""
from __future__ import annotations
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import ATCDataCoordinator
from .scheduler import ATCScheduler
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

type ATCConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ATCDataCoordinator(hass, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    scheduler = ATCScheduler(hass, coordinator)
    await scheduler.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "scheduler": scheduler,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data[DOMAIN].get(entry.entry_id, {})
    scheduler: ATCScheduler | None = domain_data.get("scheduler")
    if scheduler:
        scheduler.cancel_all()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
