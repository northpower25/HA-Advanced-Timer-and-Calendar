"""Timer templates / presets for common use cases."""
from __future__ import annotations
import copy
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Built-in template definitions
BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "irrigation_daily",
        "name": "Bewässerung (täglich)",
        "name_en": "Daily Irrigation",
        "description": "Tägliche Bewässerung einer Zone mit konfigurierbarer Dauer",
        "description_en": "Daily irrigation of one zone with configurable duration",
        "category": "irrigation",
        "icon": "mdi:water",
        "config": {
            "schedule_type": "daily",
            "time": "06:00:00",
            "enabled": True,
            "actions": [
                {
                    "entity_id": "switch.garden_valve_1",
                    "service": "switch.turn_on",
                    "duration_seconds": 600,
                }
            ],
            "conditions": None,
            "tags": ["bewässerung", "garten"],
        },
    },
    {
        "id": "irrigation_zones",
        "name": "Bewässerung (Mehrzonen)",
        "name_en": "Multi-Zone Irrigation",
        "description": "Sequenzielle Bewässerung mehrerer Zonen",
        "description_en": "Sequential irrigation of multiple zones",
        "category": "irrigation",
        "icon": "mdi:water-pump",
        "config": {
            "schedule_type": "daily",
            "time": "06:00:00",
            "enabled": True,
            "actions": [
                {"entity_id": "switch.valve_zone_1", "service": "switch.turn_on", "delay_seconds": 0, "duration_seconds": 600},
                {"entity_id": "switch.valve_zone_2", "service": "switch.turn_on", "delay_seconds": 600, "duration_seconds": 480},
                {"entity_id": "switch.valve_zone_3", "service": "switch.turn_on", "delay_seconds": 1080, "duration_seconds": 720},
            ],
            "conditions": None,
            "tags": ["bewässerung", "garten"],
        },
    },
    {
        "id": "light_morning",
        "name": "Morgendliches Licht",
        "name_en": "Morning Light",
        "description": "Licht an Wochentagen morgens einschalten",
        "description_en": "Turn on lights on weekday mornings",
        "category": "light",
        "icon": "mdi:white-balance-sunny",
        "config": {
            "schedule_type": "weekdays",
            "weekdays": [0, 1, 2, 3, 4],
            "time": "07:00:00",
            "enabled": True,
            "actions": [
                {"entity_id": "light.living_room", "service": "light.turn_on", "duration_seconds": 3600}
            ],
            "tags": ["licht", "morgen"],
        },
    },
    {
        "id": "light_sunset",
        "name": "Außenlicht bei Sonnenuntergang",
        "name_en": "Outdoor Light at Sunset",
        "description": "Außenlicht bei Sonnenuntergang automatisch einschalten",
        "description_en": "Automatically turn on outdoor lights at sunset",
        "category": "light",
        "icon": "mdi:weather-sunset",
        "config": {
            "schedule_type": "sun",
            "sun_event": "sunset",
            "sun_offset_minutes": 0,
            "enabled": True,
            "actions": [
                {"entity_id": "light.outdoor", "service": "light.turn_on"}
            ],
            "tags": ["licht", "außen"],
        },
    },
    {
        "id": "thermostat_weekday",
        "name": "Thermostat Wochentag",
        "name_en": "Weekday Thermostat",
        "description": "Temperatur an Wochentagen morgens hochsetzen",
        "description_en": "Raise temperature on weekday mornings",
        "category": "climate",
        "icon": "mdi:thermometer",
        "config": {
            "schedule_type": "weekdays",
            "weekdays": [0, 1, 2, 3, 4],
            "time": "06:30:00",
            "enabled": True,
            "actions": [
                {
                    "entity_id": "climate.living_room",
                    "service": "climate.set_temperature",
                    "service_data": {"temperature": 21},
                }
            ],
            "tags": ["heizung", "klima"],
        },
    },
    {
        "id": "vacation_mode",
        "name": "Urlaubs-Licht-Simulation",
        "name_en": "Vacation Light Simulation",
        "description": "Zufällige Lichtsteuerung zur Anwesenheitssimulation",
        "description_en": "Random light control to simulate presence",
        "category": "security",
        "icon": "mdi:home-alert",
        "config": {
            "schedule_type": "interval",
            "interval_value": 1,
            "interval_unit": "days",
            "time": "19:00:00",
            "enabled": False,
            "actions": [
                {"entity_id": "light.living_room", "service": "light.turn_on", "duration_seconds": 7200}
            ],
            "tags": ["urlaub", "sicherheit"],
        },
    },
]

CATEGORIES = {
    "irrigation": {"label_de": "Bewässerung", "label_en": "Irrigation", "icon": "mdi:water"},
    "light": {"label_de": "Licht", "label_en": "Light", "icon": "mdi:lightbulb"},
    "climate": {"label_de": "Klima / Heizung", "label_en": "Climate / Heating", "icon": "mdi:thermometer"},
    "security": {"label_de": "Sicherheit", "label_en": "Security", "icon": "mdi:shield-home"},
    "custom": {"label_de": "Benutzerdefiniert", "label_en": "Custom", "icon": "mdi:cog"},
}


def get_template(template_id: str) -> dict[str, Any] | None:
    """Return a template by ID (built-in or None)."""
    return next((t for t in BUILTIN_TEMPLATES if t["id"] == template_id), None)


def list_templates(category: str | None = None) -> list[dict[str, Any]]:
    if category:
        return [t for t in BUILTIN_TEMPLATES if t.get("category") == category]
    return list(BUILTIN_TEMPLATES)


def instantiate_template(template_id: str, name: str, overrides: dict | None = None) -> dict[str, Any] | None:
    """Create a new timer config from a template."""
    tpl = get_template(template_id)
    if not tpl:
        return None
    config = copy.deepcopy(tpl["config"])
    config["name"] = name
    config["template_id"] = template_id
    if overrides:
        config.update(overrides)
    return config
