"""Microsoft Graph API calendar provider."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .base import AbstractCalendarProvider, ExternalCalendar, ExternalCalendarEvent
from .oauth_handler import OAuthHandler

_LOGGER = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_AUTH_ENDPOINT = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_SCOPE = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"


class MicrosoftCalendarProvider(AbstractCalendarProvider):
    """Provides access to Microsoft 365 calendars via Microsoft Graph API."""

    def __init__(self, hass: HomeAssistant, account: dict[str, Any]) -> None:
        super().__init__(account)
        self.hass = hass
        self._oauth = OAuthHandler(hass, account)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.account.get('access_token', '')}",
            "Content-Type": "application/json",
        }

    def _token_endpoint(self) -> str:
        tenant = self.account.get("tenant_id", "common")
        return _TOKEN_ENDPOINT.format(tenant=tenant)

    async def async_authenticate(self) -> bool:
        """Authenticate using existing refresh token or client credentials."""
        return await self.async_refresh_token()

    async def async_refresh_token(self) -> bool:
        """Refresh the Microsoft access token."""
        refresh_token = self.account.get("refresh_token")
        if not refresh_token:
            _LOGGER.warning("No Microsoft refresh token available.")
            return False
        token_data = await self._oauth.async_refresh_access_token(
            self._token_endpoint(),
            self.account.get("client_id", ""),
            self.account.get("client_secret", ""),
            refresh_token,
            extra_params={"scope": _SCOPE},
        )
        if token_data:
            self._oauth.store_tokens(token_data)
            return True
        return False

    async def _ensure_auth(self) -> bool:
        """Ensure we have a valid access token."""
        if self.is_token_expired():
            return await self.async_refresh_token()
        return True

    async def async_list_calendars(self) -> list[ExternalCalendar]:
        """List all Microsoft 365 calendars."""
        if not await self._ensure_auth():
            return []
        session = async_get_clientsession(self.hass)
        calendars = []
        try:
            async with session.get(
                f"{_GRAPH_BASE}/me/calendars",
                headers=self._headers(),
                timeout=15,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for cal in data.get("value", []):
                        calendars.append(ExternalCalendar(
                            uid=cal["id"],
                            name=cal.get("name", ""),
                            color=cal.get("hexColor", ""),
                            read_only=not cal.get("canEdit", True),
                        ))
                else:
                    _LOGGER.warning("Graph list calendars failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Microsoft list_calendars error: %s", exc)
        return calendars

    async def async_get_events(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
    ) -> list[ExternalCalendarEvent]:
        """Get events from a Microsoft 365 calendar."""
        if not await self._ensure_auth():
            return []
        session = async_get_clientsession(self.hass)
        events = []
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$top": 100,
            "$select": "id,subject,bodyPreview,start,end,location,isAllDay,lastModifiedDateTime",
        }
        try:
            url = f"{_GRAPH_BASE}/me/calendars/{calendar_id}/calendarView"
            async with session.get(
                url, headers=self._headers(), params=params, timeout=15
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for ev in data.get("value", []):
                        start_dt = self._parse_ms_datetime(ev.get("start", {}))
                        end_dt = self._parse_ms_datetime(ev.get("end", {}))
                        events.append(ExternalCalendarEvent(
                            uid=ev["id"],
                            summary=ev.get("subject", ""),
                            start=start_dt,
                            end=end_dt,
                            description=ev.get("bodyPreview", ""),
                            location=ev.get("location", {}).get("displayName", ""),
                            all_day=ev.get("isAllDay", False),
                            calendar_id=calendar_id,
                        ))
                else:
                    _LOGGER.warning("Graph get_events failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Microsoft get_events error: %s", exc)
        return events

    def _parse_ms_datetime(self, dt_obj: dict[str, Any]) -> datetime | None:
        dt_str = dt_obj.get("dateTime", "")
        timezone = dt_obj.get("timeZone", "UTC")
        if not dt_str:
            return None
        try:
            parsed = dt_util.parse_datetime(dt_str)
            return dt_util.as_local(parsed) if parsed else None
        except (ValueError, TypeError):
            return None

    async def async_create_event(
        self,
        calendar_id: str,
        event: dict[str, Any],
    ) -> ExternalCalendarEvent | None:
        """Create a new event in a Microsoft 365 calendar."""
        if not await self._ensure_auth():
            return None
        session = async_get_clientsession(self.hass)
        payload: dict[str, Any] = {
            "subject": event.get("summary", ""),
            "body": {"contentType": "text", "content": event.get("description", "")},
            "isAllDay": event.get("all_day", False),
        }
        if event.get("start"):
            payload["start"] = {"dateTime": event["start"], "timeZone": "UTC"}
        if event.get("end"):
            payload["end"] = {"dateTime": event["end"], "timeZone": "UTC"}
        if event.get("location"):
            payload["location"] = {"displayName": event["location"]}
        try:
            async with session.post(
                f"{_GRAPH_BASE}/me/calendars/{calendar_id}/events",
                headers=self._headers(),
                json=payload,
                timeout=15,
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return ExternalCalendarEvent(
                        uid=data["id"],
                        summary=data.get("subject", ""),
                        calendar_id=calendar_id,
                    )
                _LOGGER.warning("Graph create_event failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Microsoft create_event error: %s", exc)
        return None

    async def async_update_event(
        self,
        calendar_id: str,
        event_uid: str,
        event: dict[str, Any],
    ) -> bool:
        """Update an existing event in Microsoft 365."""
        if not await self._ensure_auth():
            return False
        session = async_get_clientsession(self.hass)
        payload: dict[str, Any] = {}
        if "summary" in event:
            payload["subject"] = event["summary"]
        if "description" in event:
            payload["body"] = {"contentType": "text", "content": event["description"]}
        if "start" in event:
            payload["start"] = {"dateTime": event["start"], "timeZone": "UTC"}
        if "end" in event:
            payload["end"] = {"dateTime": event["end"], "timeZone": "UTC"}
        try:
            async with session.patch(
                f"{_GRAPH_BASE}/me/events/{event_uid}",
                headers=self._headers(),
                json=payload,
                timeout=15,
            ) as resp:
                return resp.status == 200
        except Exception as exc:
            _LOGGER.error("Microsoft update_event error: %s", exc)
        return False

    async def async_delete_event(
        self, calendar_id: str, event_uid: str
    ) -> bool:
        """Delete an event from Microsoft 365."""
        if not await self._ensure_auth():
            return False
        session = async_get_clientsession(self.hass)
        try:
            async with session.delete(
                f"{_GRAPH_BASE}/me/events/{event_uid}",
                headers=self._headers(),
                timeout=15,
            ) as resp:
                return resp.status == 204
        except Exception as exc:
            _LOGGER.error("Microsoft delete_event error: %s", exc)
        return False
