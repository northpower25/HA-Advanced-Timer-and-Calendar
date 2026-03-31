"""Notification escalation for unacknowledged ATC reminders and timers."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .coordinator import ATCDataCoordinator
    from .notifications import ATCNotificationManager

_LOGGER = logging.getLogger(__name__)

DEFAULT_ESCALATION_INTERVAL_MINUTES = 15
DEFAULT_MAX_ESCALATIONS = 3


class EscalationEntry:
    """Tracks a single pending escalation."""

    def __init__(
        self,
        entry_id: str,
        item_id: str,
        item_type: str,  # "timer" | "reminder"
        interval_minutes: int,
        max_escalations: int,
        cancel_handle,
    ) -> None:
        self.entry_id = entry_id
        self.item_id = item_id
        self.item_type = item_type
        self.interval_minutes = interval_minutes
        self.max_escalations = max_escalations
        self.count = 0
        self.cancel_handle = cancel_handle
        self.acknowledged = False


class NotificationEscalationManager:
    """Manages escalation of unacknowledged notifications."""

    def __init__(
        self,
        hass: "HomeAssistant",
        coordinator: "ATCDataCoordinator",
        notification_manager: "ATCNotificationManager",
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.notification_manager = notification_manager
        self._escalations: dict[str, EscalationEntry] = {}

    def start_escalation(
        self,
        item_id: str,
        item_type: str,
        interval_minutes: int = DEFAULT_ESCALATION_INTERVAL_MINUTES,
        max_escalations: int = DEFAULT_MAX_ESCALATIONS,
    ) -> None:
        """Start escalation tracking for an item."""
        key = f"{item_type}_{item_id}"
        if key in self._escalations:
            return  # already tracking

        cancel = self._schedule_next(key, item_id, item_type, interval_minutes, max_escalations)
        entry = EscalationEntry(
            entry_id=key,
            item_id=item_id,
            item_type=item_type,
            interval_minutes=interval_minutes,
            max_escalations=max_escalations,
            cancel_handle=cancel,
        )
        self._escalations[key] = entry
        _LOGGER.debug("Started escalation for %s %s", item_type, item_id)

    def acknowledge(self, item_id: str, item_type: str) -> bool:
        """Mark item as acknowledged and cancel escalation."""
        key = f"{item_type}_{item_id}"
        entry = self._escalations.pop(key, None)
        if entry:
            entry.acknowledged = True
            try:
                entry.cancel_handle()
            except Exception:  # noqa: BLE001
                pass
            _LOGGER.debug("Acknowledged escalation for %s %s", item_type, item_id)
            return True
        return False

    def cancel_all(self) -> None:
        """Cancel all pending escalations."""
        for entry in self._escalations.values():
            try:
                entry.cancel_handle()
            except Exception:  # noqa: BLE001
                pass
        self._escalations.clear()

    def _schedule_next(
        self,
        key: str,
        item_id: str,
        item_type: str,
        interval_minutes: int,
        max_escalations: int,
    ):
        fire_at = dt_util.utcnow() + timedelta(minutes=interval_minutes)

        @callback
        def _escalate(_now):
            self.hass.async_create_task(
                self._do_escalate(key, item_id, item_type, interval_minutes, max_escalations)
            )

        return async_track_point_in_time(self.hass, _escalate, fire_at)

    async def _do_escalate(
        self,
        key: str,
        item_id: str,
        item_type: str,
        interval_minutes: int,
        max_escalations: int,
    ) -> None:
        entry = self._escalations.get(key)
        if not entry or entry.acknowledged:
            return

        entry.count += 1
        _LOGGER.info(
            "Escalating notification for %s %s (attempt %d/%d)",
            item_type, item_id, entry.count, max_escalations,
        )

        # Re-send notification
        try:
            data = await self.coordinator.storage.async_load()
            if item_type == "reminder":
                item = next((r for r in data.get("reminders", []) if r["id"] == item_id), None)
            else:
                item = next((t for t in data.get("timers", []) if t["id"] == item_id), None)

            if item:
                await self.notification_manager.async_send(
                    item,
                    "before",
                    {"reason": f"Erinnerung (Eskalation {entry.count}/{max_escalations})"},
                )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Escalation notification failed: %s", exc)

        if entry.count < max_escalations:
            # Schedule next escalation
            cancel = self._schedule_next(key, item_id, item_type, interval_minutes, max_escalations)
            entry.cancel_handle = cancel
        else:
            # Max escalations reached
            _LOGGER.info("Max escalations reached for %s %s", item_type, item_id)
            self._escalations.pop(key, None)
