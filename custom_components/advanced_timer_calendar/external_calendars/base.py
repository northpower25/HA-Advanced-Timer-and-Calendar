"""Base classes for external calendar providers."""
from __future__ import annotations
import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ExternalCalendarEvent:
    """Represents a calendar event from an external provider."""

    uid: str
    summary: str
    start: datetime | None = None
    end: datetime | None = None
    description: str = ""
    location: str = ""
    all_day: bool = False
    calendar_id: str = ""
    last_modified: datetime | None = None
    etag: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalCalendar:
    """Represents a calendar from an external provider."""

    uid: str
    name: str
    description: str = ""
    color: str = ""
    read_only: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class AbstractCalendarProvider(abc.ABC):
    """Abstract base class for all external calendar providers."""

    def __init__(self, account: dict[str, Any]) -> None:
        self.account = account

    @abc.abstractmethod
    async def async_authenticate(self) -> bool:
        """Authenticate with the calendar provider. Returns True on success."""

    @abc.abstractmethod
    async def async_refresh_token(self) -> bool:
        """Refresh the access token if expired. Returns True on success."""

    @abc.abstractmethod
    async def async_list_calendars(self) -> list[ExternalCalendar]:
        """Return a list of available calendars."""

    @abc.abstractmethod
    async def async_get_events(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
    ) -> list[ExternalCalendarEvent]:
        """Return events in the given calendar within the time range."""

    @abc.abstractmethod
    async def async_create_event(
        self,
        calendar_id: str,
        event: dict[str, Any],
    ) -> ExternalCalendarEvent | None:
        """Create a new event. Returns the created event or None on failure."""

    @abc.abstractmethod
    async def async_update_event(
        self,
        calendar_id: str,
        event_uid: str,
        event: dict[str, Any],
    ) -> bool:
        """Update an existing event. Returns True on success."""

    @abc.abstractmethod
    async def async_delete_event(
        self,
        calendar_id: str,
        event_uid: str,
    ) -> bool:
        """Delete an event. Returns True on success."""

    def is_token_expired(self) -> bool:
        """Check if the current access token is expired."""
        from homeassistant.util import dt as dt_util
        expiry_str = self.account.get("token_expiry")
        if not expiry_str:
            return True
        try:
            expiry = dt_util.parse_datetime(expiry_str)
            if expiry is None:
                return True
            return dt_util.utcnow() >= expiry
        except (ValueError, TypeError):
            return True
