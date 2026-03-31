"""Apple Calendar (CalDAV) provider."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .base import AbstractCalendarProvider, ExternalCalendar, ExternalCalendarEvent

_LOGGER = logging.getLogger(__name__)

_APPLE_CALDAV_BASE = "https://caldav.icloud.com"

# CalDAV XML namespaces
_NS = {
    "d": "DAV:",
    "c": "urn:ietf:params:xml:ns:caldav",
    "cs": "http://calendarserver.org/ns/",
    "ical": "http://apple.com/ns/ical/",
}


class AppleCalendarProvider(AbstractCalendarProvider):
    """Provides access to Apple iCloud calendars via CalDAV."""

    def __init__(self, hass: HomeAssistant, account: dict[str, Any]) -> None:
        super().__init__(account)
        self.hass = hass

    def _caldav_url(self) -> str:
        return self.account.get("caldav_url") or _APPLE_CALDAV_BASE

    def _auth(self) -> tuple[str, str]:
        return (
            self.account.get("username", ""),
            self.account.get("password", ""),
        )

    async def async_authenticate(self) -> bool:
        """Verify CalDAV credentials are valid."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.request(
                "PROPFIND",
                self._caldav_url(),
                auth=self._auth(),
                headers={"Depth": "0", "Content-Type": "application/xml"},
                data='<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>',
                timeout=15,
            ) as resp:
                return resp.status in (200, 207)
        except Exception as exc:
            _LOGGER.error("Apple CalDAV auth error: %s", exc)
        return False

    async def async_refresh_token(self) -> bool:
        """CalDAV uses basic auth – no token refresh needed."""
        return True

    async def async_list_calendars(self) -> list[ExternalCalendar]:
        """Discover all calendars via CalDAV PROPFIND."""
        session = async_get_clientsession(self.hass)
        calendars = []
        propfind_body = (
            '<?xml version="1.0"?>'
            '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop>"
            "<d:displayname/>"
            "<d:resourcetype/>"
            "<c:calendar-description/>"
            "</d:prop>"
            "</d:propfind>"
        )
        try:
            async with session.request(
                "PROPFIND",
                self._caldav_url(),
                auth=self._auth(),
                headers={"Depth": "1", "Content-Type": "application/xml"},
                data=propfind_body,
                timeout=15,
            ) as resp:
                if resp.status == 207:
                    text = await resp.text()
                    root = ET.fromstring(text)
                    for response in root.findall(".//{DAV:}response"):
                        href = response.findtext("{DAV:}href") or ""
                        display_name = response.findtext(".//{DAV:}displayname") or href
                        resource_types = response.findall(".//{DAV:}resourcetype/{DAV:}collection")
                        calendar_type = response.findall(".//{urn:ietf:params:xml:ns:caldav}calendar")
                        if calendar_type:
                            calendars.append(ExternalCalendar(
                                uid=href,
                                name=display_name,
                            ))
                else:
                    _LOGGER.warning("Apple list_calendars failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Apple list_calendars error: %s", exc)
        return calendars

    async def async_get_events(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
    ) -> list[ExternalCalendarEvent]:
        """Get events from an Apple CalDAV calendar using REPORT."""
        session = async_get_clientsession(self.hass)
        events = []

        start_str = start.strftime("%Y%m%dT%H%M%SZ")
        end_str = end.strftime("%Y%m%dT%H%M%SZ")

        report_body = (
            '<?xml version="1.0"?>'
            '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop>"
            "<d:getetag/>"
            "<c:calendar-data/>"
            "</d:prop>"
            "<c:filter>"
            '<c:comp-filter name="VCALENDAR">'
            '<c:comp-filter name="VEVENT">'
            f'<c:time-range start="{start_str}" end="{end_str}"/>'
            "</c:comp-filter>"
            "</c:comp-filter>"
            "</c:filter>"
            "</c:calendar-query>"
        )

        url = calendar_id if calendar_id.startswith("http") else f"{self._caldav_url()}{calendar_id}"

        try:
            async with session.request(
                "REPORT",
                url,
                auth=self._auth(),
                headers={"Depth": "1", "Content-Type": "application/xml"},
                data=report_body,
                timeout=20,
            ) as resp:
                if resp.status == 207:
                    text = await resp.text()
                    events = self._parse_caldav_response(text, calendar_id)
                else:
                    _LOGGER.warning("Apple get_events failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Apple get_events error: %s", exc)
        return events

    def _parse_caldav_response(
        self, xml_text: str, calendar_id: str
    ) -> list[ExternalCalendarEvent]:
        """Parse CalDAV REPORT XML response into ExternalCalendarEvent list."""
        events = []
        try:
            root = ET.fromstring(xml_text)
            for response in root.findall(".//{DAV:}response"):
                href = response.findtext("{DAV:}href") or ""
                etag = response.findtext(".//{DAV:}getetag") or ""
                cal_data = response.findtext(
                    ".//{urn:ietf:params:xml:ns:caldav}calendar-data"
                ) or ""
                if not cal_data:
                    continue
                event = self._parse_ical_event(cal_data, href, calendar_id, etag)
                if event:
                    events.append(event)
        except ET.ParseError as exc:
            _LOGGER.warning("CalDAV XML parse error: %s", exc)
        return events

    def _parse_ical_event(
        self,
        ical_data: str,
        href: str,
        calendar_id: str,
        etag: str,
    ) -> ExternalCalendarEvent | None:
        """Parse a VEVENT from iCalendar data string."""
        uid = ""
        summary = ""
        description = ""
        location = ""
        start_dt: datetime | None = None
        end_dt: datetime | None = None
        all_day = False

        in_vevent = False
        for line in ical_data.splitlines():
            line = line.strip()
            if line == "BEGIN:VEVENT":
                in_vevent = True
                continue
            if line == "END:VEVENT":
                break
            if not in_vevent:
                continue
            if line.startswith("UID:"):
                uid = line[4:]
            elif line.startswith("SUMMARY:"):
                summary = line[8:]
            elif line.startswith("DESCRIPTION:"):
                description = line[12:]
            elif line.startswith("LOCATION:"):
                location = line[9:]
            elif line.startswith("DTSTART;VALUE=DATE:"):
                date_str = line.split(":")[-1]
                try:
                    start_dt = datetime.strptime(date_str, "%Y%m%d").replace(
                        tzinfo=dt_util.get_time_zone("UTC")
                    )
                    all_day = True
                except ValueError:
                    pass
            elif line.startswith("DTSTART"):
                dt_str = line.split(":")[-1]
                try:
                    start_dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=dt_util.get_time_zone("UTC")
                    )
                except ValueError:
                    pass
            elif line.startswith("DTEND"):
                dt_str = line.split(":")[-1]
                try:
                    end_dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(
                        tzinfo=dt_util.get_time_zone("UTC")
                    )
                except ValueError:
                    pass

        if not uid:
            return None

        return ExternalCalendarEvent(
            uid=uid,
            summary=summary,
            start=start_dt,
            end=end_dt or start_dt,
            description=description,
            location=location,
            all_day=all_day,
            calendar_id=calendar_id,
            etag=etag,
        )

    async def async_create_event(
        self,
        calendar_id: str,
        event: dict[str, Any],
    ) -> ExternalCalendarEvent | None:
        """Create a new CalDAV event."""
        import uuid as _uuid
        event_uid = str(_uuid.uuid4())
        ical = self._build_ical(event_uid, event)
        url_base = calendar_id if calendar_id.startswith("http") else f"{self._caldav_url()}{calendar_id}"
        url = f"{url_base}/{event_uid}.ics"

        session = async_get_clientsession(self.hass)
        try:
            async with session.put(
                url,
                auth=self._auth(),
                headers={"Content-Type": "text/calendar"},
                data=ical,
                timeout=15,
            ) as resp:
                if resp.status in (200, 201, 204):
                    return ExternalCalendarEvent(
                        uid=event_uid,
                        summary=event.get("summary", ""),
                        calendar_id=calendar_id,
                    )
                _LOGGER.warning("Apple create_event failed: %s", resp.status)
        except Exception as exc:
            _LOGGER.error("Apple create_event error: %s", exc)
        return None

    def _build_ical(self, uid: str, event: dict[str, Any]) -> str:
        """Build a minimal iCalendar VEVENT string."""
        now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        start = (event.get("start") or now).replace("-", "").replace(":", "").replace(" ", "T")
        end = (event.get("end") or start).replace("-", "").replace(":", "").replace(" ", "T")
        if "." in start:
            start = start.split(".")[0] + "Z"
        if "." in end:
            end = end.split(".")[0] + "Z"
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ATC//Advanced Timer Calendar//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"SUMMARY:{event.get('summary', '')}",
            f"DESCRIPTION:{event.get('description', '')}",
            f"LOCATION:{event.get('location', '')}",
            f"DTSTAMP:{now}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines)

    async def async_update_event(
        self,
        calendar_id: str,
        event_uid: str,
        event: dict[str, Any],
    ) -> bool:
        """Update an existing CalDAV event by re-creating it."""
        ical = self._build_ical(event_uid, event)
        url_base = calendar_id if calendar_id.startswith("http") else f"{self._caldav_url()}{calendar_id}"
        url = f"{url_base}/{event_uid}.ics"

        session = async_get_clientsession(self.hass)
        try:
            async with session.put(
                url,
                auth=self._auth(),
                headers={"Content-Type": "text/calendar"},
                data=ical,
                timeout=15,
            ) as resp:
                return resp.status in (200, 201, 204)
        except Exception as exc:
            _LOGGER.error("Apple update_event error: %s", exc)
        return False

    async def async_delete_event(
        self, calendar_id: str, event_uid: str
    ) -> bool:
        """Delete a CalDAV event."""
        url_base = calendar_id if calendar_id.startswith("http") else f"{self._caldav_url()}{calendar_id}"
        url = f"{url_base}/{event_uid}.ics"

        session = async_get_clientsession(self.hass)
        try:
            async with session.delete(
                url,
                auth=self._auth(),
                timeout=15,
            ) as resp:
                return resp.status in (200, 204)
        except Exception as exc:
            _LOGGER.error("Apple delete_event error: %s", exc)
        return False
