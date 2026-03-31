"""Google Calendar API v3 provider."""
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

_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_SCOPE = "https://www.googleapis.com/auth/calendar"


class GoogleCalendarProvider(AbstractCalendarProvider):
    """Provides access to Google Calendar via Calendar API v3."""

    def __init__(self, hass: HomeAssistant, account: dict[str, Any]) -> None:
        super().__init__(account)
        self.hass = hass
        self._oauth = OAuthHandler(hass, account)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.account.get('access_token', '')}",
            "Content-Type": "application/json",
        }

    async def async_authenticate(self) -> bool:
        """Authenticate using existing refresh token."""
        return await self.async_refresh_token()

    async def async_refresh_token(self) -> bool:
        """Refresh the Google access token."""
        refresh_token = self.account.get("refresh_token")
        if not refresh_token:
            _LOGGER.warning("No Google refresh token available.")
            return False
        token_data = await self._oauth.async_refresh_access_token(
            _TOKEN_ENDPOINT,
            self.account.get("client_id", ""),
            self.account.get("client_secret", ""),
            refresh_token,
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
        """List all Google calendars."""
        if not await self._ensure_auth():
            return []
        session = async_get_clientsession(self.hass)
        calendars = []
        try:
            async with session.get(
                f"{_CALENDAR_API_BASE}/users/me/calendarList",
                headers=self._headers(),
                timeout=15,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for cal in data.get("items", []):
                        calendars.append(ExternalCalendar(
                            uid=cal["id"],
                            name=cal.get("summary", ""),
                            description=cal.get("description", ""),
                            color=cal.get("backgroundColor", ""),
                            read_only=cal.get("accessRole", "reader") == "reader",
                        ))
                else:
                    _LOGGER.warning("Google list_calendars failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Google list_calendars error: %s", exc)
        return calendars

    async def async_get_events(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
    ) -> list[ExternalCalendarEvent]:
        """Get events from a Google calendar."""
        if not await self._ensure_auth():
            return []
        session = async_get_clientsession(self.hass)
        events = []
        params = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "maxResults": 250,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        try:
            async with session.get(
                f"{_CALENDAR_API_BASE}/calendars/{calendar_id}/events",
                headers=self._headers(),
                params=params,
                timeout=15,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for ev in data.get("items", []):
                        start_val = ev.get("start", {})
                        end_val = ev.get("end", {})
                        all_day = "date" in start_val and "dateTime" not in start_val
                        start_dt = self._parse_google_dt(start_val)
                        end_dt = self._parse_google_dt(end_val)
                        events.append(ExternalCalendarEvent(
                            uid=ev["id"],
                            summary=ev.get("summary", ""),
                            start=start_dt,
                            end=end_dt,
                            description=ev.get("description", ""),
                            location=ev.get("location", ""),
                            all_day=all_day,
                            calendar_id=calendar_id,
                            etag=ev.get("etag", ""),
                            last_modified=dt_util.parse_datetime(ev.get("updated", "")),
                        ))
                else:
                    _LOGGER.warning("Google get_events failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Google get_events error: %s", exc)
        return events

    def _parse_google_dt(self, dt_obj: dict[str, Any]) -> datetime | None:
        dt_str = dt_obj.get("dateTime") or dt_obj.get("date", "")
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
        """Create a new event in Google Calendar."""
        if not await self._ensure_auth():
            return None
        session = async_get_clientsession(self.hass)
        payload: dict[str, Any] = {
            "summary": event.get("summary", ""),
            "description": event.get("description", ""),
        }
        if event.get("location"):
            payload["location"] = event["location"]
        if event.get("all_day"):
            start_date = (event.get("start") or "")[:10]
            end_date = (event.get("end") or start_date)[:10]
            payload["start"] = {"date": start_date}
            payload["end"] = {"date": end_date}
        else:
            payload["start"] = {"dateTime": event.get("start", ""), "timeZone": "UTC"}
            payload["end"] = {"dateTime": event.get("end", ""), "timeZone": "UTC"}
        try:
            async with session.post(
                f"{_CALENDAR_API_BASE}/calendars/{calendar_id}/events",
                headers=self._headers(),
                json=payload,
                timeout=15,
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return ExternalCalendarEvent(
                        uid=data["id"],
                        summary=data.get("summary", ""),
                        calendar_id=calendar_id,
                    )
                _LOGGER.warning("Google create_event failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Google create_event error: %s", exc)
        return None

    async def async_update_event(
        self,
        calendar_id: str,
        event_uid: str,
        event: dict[str, Any],
    ) -> bool:
        """Update an existing Google Calendar event."""
        if not await self._ensure_auth():
            return False
        session = async_get_clientsession(self.hass)
        payload: dict[str, Any] = {}
        if "summary" in event:
            payload["summary"] = event["summary"]
        if "description" in event:
            payload["description"] = event["description"]
        if "start" in event:
            payload["start"] = {"dateTime": event["start"], "timeZone": "UTC"}
        if "end" in event:
            payload["end"] = {"dateTime": event["end"], "timeZone": "UTC"}
        if "location" in event:
            payload["location"] = event["location"]
        try:
            async with session.patch(
                f"{_CALENDAR_API_BASE}/calendars/{calendar_id}/events/{event_uid}",
                headers=self._headers(),
                json=payload,
                timeout=15,
            ) as resp:
                return resp.status == 200
        except Exception as exc:
            _LOGGER.error("Google update_event error: %s", exc)
        return False

    async def async_delete_event(
        self, calendar_id: str, event_uid: str
    ) -> bool:
        """Delete a Google Calendar event."""
        if not await self._ensure_auth():
            return False
        session = async_get_clientsession(self.hass)
        try:
            async with session.delete(
                f"{_CALENDAR_API_BASE}/calendars/{calendar_id}/events/{event_uid}",
                headers=self._headers(),
                timeout=15,
            ) as resp:
                return resp.status == 204
        except Exception as exc:
            _LOGGER.error("Google delete_event error: %s", exc)
        return False
