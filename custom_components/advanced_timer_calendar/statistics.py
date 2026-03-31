"""Statistics and history tracking for ATC timers and reminders."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .coordinator import ATCDataCoordinator

_LOGGER = logging.getLogger(__name__)

MAX_HISTORY_ENTRIES = 1000


class ATCStatistics:
    """Records and retrieves execution statistics for timers."""

    def __init__(self, hass: "HomeAssistant", coordinator: "ATCDataCoordinator") -> None:
        self.hass = hass
        self.coordinator = coordinator

    async def record_execution(
        self,
        timer_id: str,
        outcome: str,  # "fired", "skipped", "error"
        reason: str = "",
        duration_seconds: int | None = None,
    ) -> None:
        """Record a timer execution event."""
        data = await self.coordinator.storage.async_load()
        history: list[dict] = data.setdefault("execution_history", [])

        entry = {
            "timer_id": timer_id,
            "timestamp": dt_util.utcnow().isoformat(),
            "outcome": outcome,
            "reason": reason,
            "duration_seconds": duration_seconds,
        }
        history.append(entry)

        # Cap history size
        if len(history) > MAX_HISTORY_ENTRIES:
            data["execution_history"] = history[-MAX_HISTORY_ENTRIES:]

        await self.coordinator.storage.async_save(data)

    async def get_stats(self, timer_id: str, days: int = 30) -> dict[str, Any]:
        """Return execution statistics for a timer over the last N days."""
        data = await self.coordinator.storage.async_load()
        history: list[dict] = data.get("execution_history", [])

        since = dt_util.utcnow() - timedelta(days=days)
        relevant = [
            e for e in history
            if e.get("timer_id") == timer_id
            and _parse_ts(e.get("timestamp")) >= since
        ]

        fired = [e for e in relevant if e.get("outcome") == "fired"]
        skipped = [e for e in relevant if e.get("outcome") == "skipped"]
        errors = [e for e in relevant if e.get("outcome") == "error"]

        durations = [e["duration_seconds"] for e in fired if e.get("duration_seconds")]
        avg_duration = sum(durations) / len(durations) if durations else None

        return {
            "timer_id": timer_id,
            "period_days": days,
            "total_executions": len(relevant),
            "fired": len(fired),
            "skipped": len(skipped),
            "errors": len(errors),
            "skip_rate": len(skipped) / max(len(relevant), 1),
            "avg_duration_seconds": avg_duration,
            "last_fired": fired[-1]["timestamp"] if fired else None,
            "last_skipped": skipped[-1]["timestamp"] if skipped else None,
        }

    async def get_history(
        self,
        timer_id: str | None = None,
        days: int = 7,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return raw execution history entries, newest first."""
        data = await self.coordinator.storage.async_load()
        history: list[dict] = data.get("execution_history", [])
        since = dt_util.utcnow() - timedelta(days=days)
        results = [
            e for e in history
            if (timer_id is None or e.get("timer_id") == timer_id)
            and _parse_ts(e.get("timestamp")) >= since
        ]
        return list(reversed(results))[-limit:]

    async def clear_history(self, timer_id: str | None = None) -> int:
        """Clear history for a timer (or all). Returns count deleted."""
        data = await self.coordinator.storage.async_load()
        history: list[dict] = data.get("execution_history", [])
        if timer_id:
            before = len(history)
            data["execution_history"] = [e for e in history if e.get("timer_id") != timer_id]
            removed = before - len(data["execution_history"])
        else:
            removed = len(history)
            data["execution_history"] = []
        await self.coordinator.storage.async_save(data)
        return removed


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=dt_util.UTC)
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_util.UTC)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=dt_util.UTC)
