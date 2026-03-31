"""Import/Export functionality for ATC timers and reminders."""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .coordinator import ATCDataCoordinator

_LOGGER = logging.getLogger(__name__)

EXPORT_VERSION = "1.0"


class ATCImportExport:
    """Handles import and export of ATC configuration."""

    def __init__(self, hass: "HomeAssistant", coordinator: "ATCDataCoordinator") -> None:
        self.hass = hass
        self.coordinator = coordinator

    # ---- Export ----

    async def export_all(self) -> dict[str, Any]:
        """Export all timers and reminders as a JSON-serialisable dict."""
        data = await self.coordinator.storage.async_load()
        return {
            "atc_export_version": EXPORT_VERSION,
            "timers": data.get("timers", []),
            "reminders": data.get("reminders", []),
            "settings": data.get("settings", {}),
        }

    async def export_timers(self, timer_ids: list[str] | None = None) -> dict[str, Any]:
        """Export selected timers (all if timer_ids is None)."""
        data = await self.coordinator.storage.async_load()
        timers = data.get("timers", [])
        if timer_ids:
            timers = [t for t in timers if t["id"] in timer_ids]
        return {"atc_export_version": EXPORT_VERSION, "timers": timers}

    async def export_reminders(self, reminder_ids: list[str] | None = None) -> dict[str, Any]:
        """Export selected reminders."""
        data = await self.coordinator.storage.async_load()
        reminders = data.get("reminders", [])
        if reminder_ids:
            reminders = [r for r in reminders if r["id"] in reminder_ids]
        return {"atc_export_version": EXPORT_VERSION, "reminders": reminders}

    def to_json(self, export_data: dict) -> str:
        """Serialise export dict to JSON string."""
        return json.dumps(export_data, indent=2, ensure_ascii=False, default=str)

    # ---- Import ----

    async def import_json(self, json_str: str, merge: bool = True) -> dict[str, Any]:
        """
        Import from JSON string.
        merge=True: add imported items (skip duplicates by ID).
        merge=False: replace all timers/reminders.
        Returns: {imported_timers: int, imported_reminders: int, errors: list}
        """
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return {"imported_timers": 0, "imported_reminders": 0, "errors": [str(exc)]}

        errors: list[str] = []
        imported_timers = 0
        imported_reminders = 0

        data = await self.coordinator.storage.async_load()

        # Import timers
        incoming_timers = payload.get("timers", [])
        if incoming_timers:
            existing_ids = {t["id"] for t in data.get("timers", [])}
            if not merge:
                data["timers"] = []
                existing_ids = set()
            for timer in incoming_timers:
                if not isinstance(timer, dict) or "name" not in timer:
                    errors.append(f"Invalid timer: {timer.get('id', '?')}")
                    continue
                if merge and timer.get("id") in existing_ids:
                    _LOGGER.debug("Skipping duplicate timer %s", timer.get("id"))
                    continue
                # Assign new ID to avoid conflicts
                from .storage import ATCStorage
                timer = dict(timer)
                timer["id"] = ATCStorage.new_id()
                data.setdefault("timers", []).append(timer)
                imported_timers += 1

        # Import reminders
        incoming_reminders = payload.get("reminders", [])
        if incoming_reminders:
            existing_ids = {r["id"] for r in data.get("reminders", [])}
            if not merge:
                data["reminders"] = []
                existing_ids = set()
            for reminder in incoming_reminders:
                if not isinstance(reminder, dict) or "name" not in reminder:
                    errors.append(f"Invalid reminder: {reminder.get('id', '?')}")
                    continue
                if merge and reminder.get("id") in existing_ids:
                    continue
                from .storage import ATCStorage
                reminder = dict(reminder)
                reminder["id"] = ATCStorage.new_id()
                data.setdefault("reminders", []).append(reminder)
                imported_reminders += 1

        await self.coordinator.storage.async_save(data)
        await self.coordinator.async_request_refresh()

        return {
            "imported_timers": imported_timers,
            "imported_reminders": imported_reminders,
            "errors": errors,
        }

    async def generate_ha_automation_yaml(self, timer_id: str) -> str:
        """Generate the equivalent HA automation YAML for a timer (expert mode)."""
        import yaml  # HA ships with PyYAML
        data = await self.coordinator.storage.async_load()
        timer = next((t for t in data.get("timers", []) if t["id"] == timer_id), None)
        if not timer:
            return "# Timer not found"

        automation: dict[str, Any] = {
            "alias": f"ATC: {timer.get('name', 'Timer')}",
            "description": f"Generated by ATC – Timer ID: {timer_id}",
            "mode": "single",
            "trigger": _build_trigger(timer),
            "condition": _build_condition(timer.get("conditions")),
            "action": _build_actions(timer.get("actions", [])),
        }
        return yaml.dump(automation, allow_unicode=True, default_flow_style=False)


# ---- YAML helpers ----

def _build_trigger(timer: dict) -> list[dict]:
    schedule_type = timer.get("schedule_type", "daily")
    time_val = timer.get("time", "06:00:00")
    if schedule_type in ("daily", "once"):
        return [{"platform": "time", "at": time_val}]
    if schedule_type == "weekdays":
        weekdays = timer.get("weekdays", [])
        day_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
        days_str = ",".join(day_map[d] for d in weekdays if d in day_map)
        return [{"platform": "time", "at": time_val, "weekday": days_str}]
    if schedule_type == "sun":
        sun_event = timer.get("sun_event", "sunrise")
        offset = timer.get("sun_offset_minutes", 0)
        return [{"platform": "sun", "event": sun_event, "offset": f"{offset:+d}:00"}]
    return [{"platform": "time", "at": time_val}]


def _build_condition(conditions: dict | None) -> list[dict]:
    if not conditions:
        return []
    return [_condition_node_to_ha(conditions)]


def _condition_node_to_ha(node: dict) -> dict:
    if node.get("type") == "group":
        operator = node.get("operator", "and")
        children = [_condition_node_to_ha(c) for c in node.get("conditions", [])]
        return {"condition": operator, "conditions": children}
    # item
    ctype = node.get("condition_type", "state")
    entity = node.get("entity_id", "")
    if ctype == "state":
        return {"condition": "state", "entity_id": entity, "state": node.get("value")}
    if ctype == "numeric_below":
        return {"condition": "numeric_state", "entity_id": entity, "below": node.get("value")}
    if ctype == "numeric_above":
        return {"condition": "numeric_state", "entity_id": entity, "above": node.get("value")}
    if ctype == "numeric_between":
        return {"condition": "numeric_state", "entity_id": entity, "above": node.get("min_value"), "below": node.get("max_value")}
    if ctype == "template":
        return {"condition": "template", "value_template": node.get("template", "")}
    return {}


def _build_actions(actions: list[dict]) -> list[dict]:
    ha_actions: list[dict] = []
    for action in actions:
        delay = action.get("delay_seconds", 0)
        if delay:
            ha_actions.append({"delay": {"seconds": delay}})
        service = action.get("service", "homeassistant.turn_on")
        ha_actions.append({
            "service": service,
            "target": {"entity_id": action.get("entity_id", "")},
            "data": action.get("service_data", {}),
        })
        duration = action.get("duration_seconds")
        if duration:
            ha_actions.append({"delay": {"seconds": duration}})
            entity_id = action.get("entity_id", "")
            domain = entity_id.split(".")[0] if entity_id else "homeassistant"
            ha_actions.append({
                "service": f"{domain}.turn_off",
                "target": {"entity_id": entity_id},
            })
    return ha_actions
