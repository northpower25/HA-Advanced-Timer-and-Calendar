"""Central DataUpdateCoordinator for ATC."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .storage import ATCStorage

_LOGGER = logging.getLogger(__name__)


class ATCDataCoordinator(DataUpdateCoordinator):
    """Coordinator holding all ATC state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.storage = ATCStorage(hass, entry_id)
        self.entry_id = entry_id

    async def _async_update_data(self) -> dict[str, Any]:
        return await self.storage.async_load()
