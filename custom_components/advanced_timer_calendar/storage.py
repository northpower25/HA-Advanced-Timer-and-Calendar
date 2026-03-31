"""Persistence via HA Storage API with schema migration."""
from __future__ import annotations
import logging
import uuid
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

EMPTY_DATA: dict[str, Any] = {
    "schema_version": STORAGE_VERSION,
    "timers": [],
    "reminders": [],
    "calendar_accounts": [],
    "calendar_triggers": [],
    "external_events": [],
    "settings": {
        "default_reminder_minutes": 30,
        "timezone": None,
    },
}


class ATCStorage:
    """Handles persistent storage for ATC with migration support."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry_id}")
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        raw = await self._store.async_load()
        if raw is None:
            self._data = dict(EMPTY_DATA)
            return self._data
        try:
            self._data = await self._migrate(raw)
        except Exception as exc:
            _LOGGER.error("Storage migration failed: %s – loading empty data", exc)
            self._data = dict(EMPTY_DATA)
        return self._data

    async def async_save(self, data: dict[str, Any] | None = None) -> None:
        if data is not None:
            self._data = data
        if self._data is not None:
            await self._store.async_save(self._data)

    async def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        version = data.get("schema_version", 1)
        if version == STORAGE_VERSION:
            for key, val in EMPTY_DATA.items():
                data.setdefault(key, val if not isinstance(val, dict) else dict(val))
            return data
        return data

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())
