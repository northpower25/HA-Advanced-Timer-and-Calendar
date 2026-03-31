"""Telegram bot integration for HA Advanced Timer & Calendar."""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, TelegramMode

_LOGGER = logging.getLogger(__name__)

_BOT_API_BASE = "https://api.telegram.org/bot{token}"


class ATCTelegramBot:
    """Handles Telegram notifications and command processing for ATC."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.config = config
        self._token: str = config.get("telegram_bot_token", "")
        self._default_chat_id: str = config.get("telegram_chat_id", "")
        self._notify_service: str = config.get("telegram_notify_service", "")
        self._mode: str = config.get("telegram_mode", TelegramMode.NONE)
        self._allowed_chat_ids: list[str] = [
            cid.strip()
            for cid in config.get("telegram_allowed_chat_ids", self._default_chat_id).split(",")
            if cid.strip()
        ]
        self._polling_task: asyncio.Task | None = None
        self._polling_active: bool = False
        self._last_update_id: int = 0

    def _api_url(self, method: str) -> str:
        base = _BOT_API_BASE.format(token=self._token)
        return f"{base}/{method}"

    def _is_allowed(self, chat_id: str) -> bool:
        if not self._allowed_chat_ids:
            return True
        return str(chat_id) in self._allowed_chat_ids

    async def async_send_message(
        self,
        chat_id: str,
        text: str,
        inline_keyboard: list[list[dict]] | None = None,
    ) -> bool:
        """Send a Telegram message using the configured mode."""
        if not chat_id:
            chat_id = self._default_chat_id
        if not chat_id:
            _LOGGER.warning("No Telegram chat_id configured.")
            return False

        if self._mode == TelegramMode.MODE_A:
            return await self._send_via_bot_api(chat_id, text, inline_keyboard)
        elif self._mode == TelegramMode.MODE_B:
            return await self._send_via_ha_service(chat_id, text, inline_keyboard)
        return False

    async def _send_via_bot_api(
        self,
        chat_id: str,
        text: str,
        inline_keyboard: list[list[dict]] | None = None,
    ) -> bool:
        """Send message directly via Telegram Bot API."""
        if not self._token:
            _LOGGER.warning("Telegram bot token not configured.")
            return False
        session = async_get_clientsession(self.hass)
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        try:
            async with session.post(
                self._api_url("sendMessage"), json=payload, timeout=10
            ) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                _LOGGER.warning("Telegram API error %s: %s", resp.status, body)
                return False
        except Exception as exc:
            _LOGGER.error("Telegram send error: %s", exc)
            return False

    async def _send_via_ha_service(
        self,
        chat_id: str,
        text: str,
        inline_keyboard: list[list[dict]] | None = None,
    ) -> bool:
        """Send message via HA telegram_bot service."""
        try:
            service_data: dict[str, Any] = {
                "message": text,
                "target": int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id,
            }
            if inline_keyboard:
                service_data["inline_keyboard"] = inline_keyboard
            await self.hass.services.async_call(
                "telegram_bot",
                "send_message",
                service_data,
                blocking=False,
            )
            return True
        except Exception as exc:
            _LOGGER.error("HA telegram_bot service error: %s", exc)
            return False

    async def async_get_updates(self, offset: int = 0) -> list[dict[str, Any]]:
        """Fetch pending updates from Telegram Bot API (long polling)."""
        if not self._token:
            return []
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                self._api_url("getUpdates"),
                params={"offset": offset, "timeout": 30, "limit": 100},
                timeout=35,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("result", [])
        except Exception as exc:
            _LOGGER.debug("getUpdates error: %s", exc)
        return []

    async def async_set_webhook(self, url: str) -> bool:
        """Register a webhook URL with Telegram."""
        if not self._token:
            return False
        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                self._api_url("setWebhook"),
                json={"url": url},
                timeout=10,
            ) as resp:
                return resp.status == 200
        except Exception as exc:
            _LOGGER.error("setWebhook error: %s", exc)
            return False

    async def async_start_polling(self) -> None:
        """Start long-polling for incoming Telegram updates."""
        if self._polling_active:
            return
        self._polling_active = True
        self._polling_task = asyncio.create_task(self._poll_loop())

    async def async_stop_polling(self) -> None:
        """Stop the long-polling loop."""
        self._polling_active = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None

    async def _poll_loop(self) -> None:
        """Long-polling loop."""
        while self._polling_active:
            try:
                updates = await self.async_get_updates(self._last_update_id)
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id >= self._last_update_id:
                        self._last_update_id = update_id + 1
                    await self.async_handle_command(update)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.debug("Poll loop error: %s", exc)
                await asyncio.sleep(5)

    async def async_handle_command(self, update: dict[str, Any]) -> None:
        """Process an incoming Telegram update/command."""
        message = update.get("message") or update.get("edited_message", {})
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if not self._is_allowed(chat_id):
            _LOGGER.warning("Rejected Telegram message from disallowed chat_id: %s", chat_id)
            return

        text: str = message.get("text", "")
        if not text.startswith("/"):
            return

        command = text.split()[0].lower().lstrip("/")
        args = text.split()[1:]

        if command == "help":
            await self._cmd_help(chat_id)
        elif command == "status":
            await self._cmd_status(chat_id)
        elif command == "timer":
            await self._cmd_timer(chat_id, args)
        elif command == "reminder":
            await self._cmd_reminder(chat_id, args)
        else:
            await self.async_send_message(
                chat_id,
                "Unknown command. Use /help for a list of commands.",
            )

    async def _cmd_help(self, chat_id: str) -> None:
        msg = (
            "<b>ATC Bot Commands</b>\n"
            "/status – Show system status\n"
            "/timer list – List all timers\n"
            "/timer run &lt;id&gt; – Run timer immediately\n"
            "/reminder list – List upcoming reminders\n"
            "/help – Show this help"
        )
        await self.async_send_message(chat_id, msg)

    async def _cmd_status(self, chat_id: str) -> None:
        domain_data = self.hass.data.get(DOMAIN, {})
        total_timers = 0
        enabled_timers = 0
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "coordinator" in entry_data:
                coordinator = entry_data["coordinator"]
                data = coordinator.data or {}
                timers = data.get("timers", [])
                total_timers += len(timers)
                enabled_timers += sum(1 for t in timers if t.get("enabled"))
        msg = (
            f"<b>ATC Status</b>\n"
            f"Timers: {enabled_timers}/{total_timers} enabled"
        )
        await self.async_send_message(chat_id, msg)

    async def _cmd_timer(self, chat_id: str, args: list[str]) -> None:
        if not args:
            await self.async_send_message(chat_id, "Usage: /timer list | /timer run &lt;id&gt;")
            return

        subcommand = args[0].lower()
        domain_data = self.hass.data.get(DOMAIN, {})

        if subcommand == "list":
            lines = ["<b>Timers:</b>"]
            for entry_data in domain_data.values():
                if isinstance(entry_data, dict) and "coordinator" in entry_data:
                    data = entry_data["coordinator"].data or {}
                    for timer in data.get("timers", []):
                        state = "✅" if timer.get("enabled") else "❌"
                        lines.append(f"{state} {timer['name']} ({timer['id'][:8]})")
            await self.async_send_message(chat_id, "\n".join(lines) or "No timers configured.")

        elif subcommand == "run" and len(args) > 1:
            timer_id_prefix = args[1]
            for entry_data in domain_data.values():
                if isinstance(entry_data, dict) and "scheduler" in entry_data:
                    data = entry_data["coordinator"].data or {}
                    for timer in data.get("timers", []):
                        if timer["id"].startswith(timer_id_prefix):
                            await entry_data["scheduler"]._fire_timer(timer["id"])
                            await self.async_send_message(chat_id, f"Timer '{timer['name']}' triggered.")
                            return
            await self.async_send_message(chat_id, "Timer not found.")

    async def _cmd_reminder(self, chat_id: str, args: list[str]) -> None:
        domain_data = self.hass.data.get(DOMAIN, {})
        lines = ["<b>Upcoming Reminders:</b>"]
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "coordinator" in entry_data:
                data = entry_data["coordinator"].data or {}
                for reminder in data.get("reminders", []):
                    if not reminder.get("completed", False):
                        dt_str = reminder.get("datetime") or reminder.get("due_date") or ""
                        lines.append(f"• {reminder['name']} – {dt_str}")
        await self.async_send_message(chat_id, "\n".join(lines) or "No pending reminders.")
