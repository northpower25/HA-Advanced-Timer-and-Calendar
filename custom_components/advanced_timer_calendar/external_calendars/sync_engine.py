"""Bidirectional sync engine for external calendars."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import SyncDirection, ConflictStrategy
from .base import ExternalCalendarEvent

_LOGGER = logging.getLogger(__name__)


class ATCSyncEngine:
    """Orchestrates bidirectional sync between HA and external calendars."""

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator

    def _get_provider(self, account: dict[str, Any]):
        """Instantiate the correct provider for the given account."""
        from . import get_provider
        provider_cls = get_provider(account.get("provider", ""))
        if provider_cls is None:
            _LOGGER.warning("Unknown provider: %s", account.get("provider"))
            return None
        return provider_cls(self.hass, account)

    async def async_sync(self, account_id: str | None = None) -> None:
        """Sync all accounts (or a specific one) with their external calendars."""
        data = await self.coordinator.storage.async_load()
        accounts = data.get("calendar_accounts", [])

        for account in accounts:
            if account_id and account["id"] != account_id:
                continue
            await self._sync_account(account, data)

        await self.coordinator.storage.async_save(data)

    async def _sync_account(
        self, account: dict[str, Any], data: dict[str, Any]
    ) -> None:
        """Perform sync for a single account."""
        account_id = account["id"]
        _LOGGER.info("Starting sync for account %s (%s)", account.get("name"), account_id)

        account["sync_status"] = "syncing"
        provider = self._get_provider(account)
        if provider is None:
            account["sync_status"] = "error"
            return

        try:
            if not await provider.async_authenticate():
                _LOGGER.warning("Authentication failed for account %s", account_id)
                account["sync_status"] = "auth_error"
                return

            direction = account.get("sync_direction", SyncDirection.BIDIRECTIONAL)
            now = dt_util.now()
            start = now - timedelta(days=30)
            end = now + timedelta(days=365)

            calendar_ids = account.get("calendars") or []
            if not calendar_ids:
                remote_calendars = await provider.async_list_calendars()
                calendar_ids = [c.uid for c in remote_calendars]

            for calendar_id in calendar_ids:
                if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
                    await self._sync_inbound(account, provider, calendar_id, start, end, data)

                if direction in (SyncDirection.OUTBOUND, SyncDirection.BIDIRECTIONAL):
                    await self._sync_outbound(account, provider, calendar_id, data)

            account["sync_status"] = "ok"
            account["last_sync"] = dt_util.now().isoformat()

        except Exception as exc:
            _LOGGER.error("Sync error for account %s: %s", account_id, exc)
            account["sync_status"] = "error"

    async def _sync_inbound(
        self,
        account: dict[str, Any],
        provider,
        calendar_id: str,
        start: datetime,
        end: datetime,
        data: dict[str, Any],
    ) -> None:
        """Pull remote events and upsert into local external_events storage."""
        remote_events = await provider.async_get_events(calendar_id, start, end)
        existing_ids = {
            e["uid"]: e
            for e in data.get("external_events", [])
            if e.get("account_id") == account["id"] and e.get("calendar_id") == calendar_id
        }

        for remote in remote_events:
            local = existing_ids.get(remote.uid)
            if local is None:
                # New remote event – add to local storage
                data.setdefault("external_events", []).append(
                    self._remote_to_local(remote, account["id"])
                )
            else:
                conflict_strategy = account.get("conflict_strategy", ConflictStrategy.NEWEST_WINS)
                self._resolve_conflict(local, remote, conflict_strategy)

    async def _sync_outbound(
        self,
        account: dict[str, Any],
        provider,
        calendar_id: str,
        data: dict[str, Any],
    ) -> None:
        """Push locally created/modified events to the remote calendar."""
        pending = [
            e for e in data.get("external_events", [])
            if e.get("account_id") == account["id"]
            and e.get("calendar_id") == calendar_id
            and e.get("local_only", False)
        ]
        for event in pending:
            result = await provider.async_create_event(calendar_id, event)
            if result:
                event["local_only"] = False
                event["uid"] = result.uid

    def _remote_to_local(
        self, remote: ExternalCalendarEvent, account_id: str
    ) -> dict[str, Any]:
        """Convert an ExternalCalendarEvent to local storage dict."""
        return {
            "uid": remote.uid,
            "account_id": account_id,
            "calendar_id": remote.calendar_id,
            "summary": remote.summary,
            "description": remote.description,
            "start": remote.start.isoformat() if remote.start else None,
            "end": remote.end.isoformat() if remote.end else None,
            "location": remote.location,
            "all_day": remote.all_day,
            "etag": remote.etag,
            "last_modified": remote.last_modified.isoformat() if remote.last_modified else None,
            "local_only": False,
        }

    def _resolve_conflict(
        self,
        local: dict[str, Any],
        remote: ExternalCalendarEvent,
        strategy: str,
    ) -> None:
        """Apply conflict resolution strategy."""
        if strategy == ConflictStrategy.REMOTE_WINS:
            local["summary"] = remote.summary
            local["description"] = remote.description
            local["start"] = remote.start.isoformat() if remote.start else None
            local["end"] = remote.end.isoformat() if remote.end else None
        elif strategy == ConflictStrategy.HA_WINS:
            pass  # Keep local data
        elif strategy == ConflictStrategy.NEWEST_WINS:
            remote_modified = remote.last_modified
            local_modified_str = local.get("last_modified")
            if remote_modified and local_modified_str:
                try:
                    local_modified = dt_util.parse_datetime(local_modified_str)
                    if local_modified and remote_modified > local_modified:
                        local["summary"] = remote.summary
                        local["description"] = remote.description
                        local["start"] = remote.start.isoformat() if remote.start else None
                        local["end"] = remote.end.isoformat() if remote.end else None
                except (ValueError, TypeError):
                    pass
            elif remote_modified:
                local["summary"] = remote.summary
        # MANUAL: no automatic resolution, flag for user

    async def async_create_event(
        self,
        account_id: str,
        calendar_id: str,
        event: dict[str, Any],
    ) -> None:
        """Create an event in an external calendar and store locally."""
        data = await self.coordinator.storage.async_load()
        account = next(
            (a for a in data.get("calendar_accounts", []) if a["id"] == account_id),
            None,
        )
        if account is None:
            _LOGGER.warning("Account %s not found.", account_id)
            return

        provider = self._get_provider(account)
        if provider is None:
            return

        if not await provider.async_authenticate():
            _LOGGER.warning("Authentication failed for account %s", account_id)
            return

        result = await provider.async_create_event(calendar_id, event)
        if result:
            local_event = self._remote_to_local(result, account_id)
            local_event["calendar_id"] = calendar_id
            local_event["summary"] = event.get("summary", "")
            local_event["description"] = event.get("description", "")
            data.setdefault("external_events", []).append(local_event)
            await self.coordinator.storage.async_save(data)

    async def async_delete_event(
        self,
        account_id: str,
        calendar_id: str,
        event_id: str,
    ) -> None:
        """Delete an event from an external calendar and remove from local storage."""
        data = await self.coordinator.storage.async_load()
        account = next(
            (a for a in data.get("calendar_accounts", []) if a["id"] == account_id),
            None,
        )
        if account is None:
            _LOGGER.warning("Account %s not found.", account_id)
            return

        provider = self._get_provider(account)
        if provider is None:
            return

        if not await provider.async_authenticate():
            return

        success = await provider.async_delete_event(calendar_id, event_id)
        if success:
            data["external_events"] = [
                e for e in data.get("external_events", [])
                if not (e.get("uid") == event_id and e.get("account_id") == account_id)
            ]
            await self.coordinator.storage.async_save(data)
