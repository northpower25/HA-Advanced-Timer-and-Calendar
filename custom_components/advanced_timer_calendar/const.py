"""Constants for HA Advanced Timer & Calendar."""
from __future__ import annotations
from enum import StrEnum

DOMAIN = "advanced_timer_calendar"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

PLATFORMS = ["switch", "sensor", "calendar", "todo"]


class ScheduleType(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    INTERVAL = "interval"
    YEARLY = "yearly"
    CRON = "cron"
    SUN = "sun"


class IntervalUnit(StrEnum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class SunEvent(StrEnum):
    SUNRISE = "sunrise"
    SUNSET = "sunset"


class TimerStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    SKIPPED = "skipped"
    ERROR = "error"


class ReminderType(StrEnum):
    REMINDER = "reminder"
    TODO = "todo"
    ANNIVERSARY = "anniversary"
    APPOINTMENT = "appointment"


class TelegramMode(StrEnum):
    NONE = "none"
    MODE_A = "mode_a"
    MODE_B = "mode_b"


class VoiceProvider(StrEnum):
    NONE = "none"
    ALEXA = "alexa_media_player"
    GOOGLE_CAST = "google_cast"
    SONOS = "sonos"
    GENERIC_TTS = "generic_tts"


class NotificationEvent(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    RESET = "reset"
    SKIPPED = "skipped"
    ERROR = "error"


class SyncDirection(StrEnum):
    BIDIRECTIONAL = "bidirectional"
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ConflictStrategy(StrEnum):
    HA_WINS = "ha_wins"
    REMOTE_WINS = "remote_wins"
    NEWEST_WINS = "newest_wins"
    MANUAL = "manual"


SERVICE_CREATE_TIMER = "create_timer"
SERVICE_UPDATE_TIMER = "update_timer"
SERVICE_DELETE_TIMER = "delete_timer"
SERVICE_ENABLE_TIMER = "enable_timer"
SERVICE_DISABLE_TIMER = "disable_timer"
SERVICE_PAUSE_TIMER = "pause_timer"
SERVICE_SKIP_NEXT = "skip_next"
SERVICE_RUN_NOW = "run_now"
SERVICE_CREATE_REMINDER = "create_reminder"
SERVICE_COMPLETE_TODO = "complete_todo"
SERVICE_SYNC_CALENDAR = "sync_calendar"
SERVICE_ADD_CALENDAR_ACCOUNT = "add_calendar_account"
SERVICE_REMOVE_CALENDAR_ACCOUNT = "remove_calendar_account"
SERVICE_CREATE_EXTERNAL_EVENT = "create_external_event"
SERVICE_DELETE_EXTERNAL_EVENT = "delete_external_event"
SERVICE_CREATE_CALENDAR_TRIGGER = "create_calendar_trigger"
SERVICE_DELETE_CALENDAR_TRIGGER = "delete_calendar_trigger"

DEFAULT_TEMPLATES = {
    "before": "⏰ {{ name }} startet in {{ time_until }}.",
    "after": "✅ {{ name }} wurde gestartet.",
    "reset": "🔄 {{ name }} wurde abgeschlossen und zurückgesetzt.",
    "skipped": "⏭ {{ name }} wurde übersprungen ({{ reason }}).",
    "voice_before": "{{ name }} startet in {{ time_until }}.",
    "voice_after": "{{ name }} wurde gestartet.",
    "voice_reset": "{{ name }} wurde abgeschlossen.",
    "voice_skipped": "{{ name }} wurde übersprungen.",
}
