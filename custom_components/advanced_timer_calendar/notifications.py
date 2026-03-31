"""Notification manager for HA Advanced Timer & Calendar."""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .const import DOMAIN, TelegramMode, VoiceProvider, NotificationEvent, DEFAULT_TEMPLATES

_LOGGER = logging.getLogger(__name__)


class ATCNotificationManager:
    """Dispatches notifications for timer and reminder events."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _get_config(self) -> dict[str, Any]:
        """Get integration config from the first available entry."""
        domain_data = self.hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "coordinator" in entry_data:
                coordinator = entry_data["coordinator"]
                entry = self.hass.config_entries.async_get_entry(coordinator.entry_id)
                if entry:
                    cfg = dict(entry.options or entry.data)
                    return cfg
        return {}

    def _render_template(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template string with provided variables."""
        try:
            tmpl = Template(template_str, self.hass)
            return str(tmpl.async_render(variables))
        except Exception as exc:
            _LOGGER.warning("Template render error: %s", exc)
            return template_str

    def _build_message(
        self,
        item: dict[str, Any],
        event_type: str,
        context: dict[str, Any],
    ) -> str:
        """Build a notification message from templates or defaults."""
        notifications = item.get("notifications", {})
        template_key = event_type
        template_str = notifications.get(f"template_{event_type}") or DEFAULT_TEMPLATES.get(template_key, "")
        variables = {
            "name": item.get("name", "Timer"),
            "time_until": context.get("time_until", ""),
            "reason": context.get("reason", ""),
            **context,
        }
        return self._render_template(template_str, variables)

    async def async_send(
        self,
        item: dict[str, Any],
        event_type: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Dispatch notifications to all configured channels."""
        if context is None:
            context = {}

        notifications = item.get("notifications", {})
        if not notifications:
            return

        message = self._build_message(item, event_type, context)
        config = self._get_config()

        # HA notify service
        notify_service = notifications.get("notify_service") or config.get("notify_service", "")
        if notify_service:
            await self._send_ha_notify(notify_service, message, item.get("name", "ATC"))

        # Telegram
        telegram_mode = config.get("telegram_mode", TelegramMode.NONE)
        if telegram_mode != TelegramMode.NONE and notifications.get("telegram", False):
            await self._send_telegram(config, message, telegram_mode)

        # Voice
        voice_provider = config.get("voice_provider", VoiceProvider.NONE)
        if voice_provider != VoiceProvider.NONE and notifications.get("voice", False):
            voice_template_key = f"voice_{event_type}"
            voice_template_str = notifications.get(f"voice_template_{event_type}") or DEFAULT_TEMPLATES.get(voice_template_key, message)
            variables = {
                "name": item.get("name", "Timer"),
                "time_until": context.get("time_until", ""),
                "reason": context.get("reason", ""),
                **context,
            }
            voice_message = self._render_template(voice_template_str, variables)
            await self._send_voice(config, voice_message)

    async def _send_ha_notify(
        self, service: str, message: str, title: str
    ) -> None:
        """Send via HA notify service."""
        try:
            parts = service.split(".", 1)
            if len(parts) == 2:
                domain, svc = parts
            else:
                domain, svc = "notify", parts[0]
            await self.hass.services.async_call(
                domain,
                svc,
                {"message": message, "title": title},
                blocking=False,
            )
        except Exception as exc:
            _LOGGER.warning("HA notify error (%s): %s", service, exc)

    async def _send_telegram(
        self, config: dict[str, Any], message: str, mode: str
    ) -> None:
        """Send via Telegram."""
        try:
            from .telegram_bot import ATCTelegramBot
            bot = ATCTelegramBot(self.hass, config)
            await bot.async_send_message(
                config.get("telegram_chat_id", ""),
                message,
            )
        except Exception as exc:
            _LOGGER.warning("Telegram send error: %s", exc)

    async def _send_voice(
        self, config: dict[str, Any], message: str
    ) -> None:
        """Send via voice announcement."""
        try:
            from .voice_notifications import ATCVoiceNotifier
            await ATCVoiceNotifier.async_announce(self.hass, message, config)
        except Exception as exc:
            _LOGGER.warning("Voice notification error: %s", exc)
