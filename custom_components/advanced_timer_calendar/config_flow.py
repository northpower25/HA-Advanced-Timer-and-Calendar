"""Config flow for HA Advanced Timer & Calendar."""
from __future__ import annotations
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import DOMAIN, TelegramMode, VoiceProvider

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default="ATC"): str,
})

STEP_TELEGRAM_SCHEMA = vol.Schema({
    vol.Optional("telegram_mode", default=TelegramMode.NONE): vol.In(
        [m.value for m in TelegramMode]
    ),
    vol.Optional("telegram_bot_token", default=""): str,
    vol.Optional("telegram_chat_id", default=""): str,
    vol.Optional("telegram_notify_service", default=""): str,
})

STEP_VOICE_SCHEMA = vol.Schema({
    vol.Optional("voice_provider", default=VoiceProvider.NONE): vol.In(
        [p.value for p in VoiceProvider]
    ),
    vol.Optional("voice_media_player", default=""): str,
    vol.Optional("voice_volume", default=0.5): vol.All(
        vol.Coerce(float), vol.Range(min=0.0, max=1.0)
    ),
    vol.Optional("voice_tts_engine", default=""): str,
    vol.Optional("voice_language", default=""): str,
})

STEP_SETTINGS_SCHEMA = vol.Schema({
    vol.Optional("default_reminder_minutes", default=30): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=10080)
    ),
    vol.Optional("timezone", default=""): str,
})


class ATCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration flow for ATC."""

    VERSION = 1
    _data: dict[str, Any]

    def __init__(self) -> None:
        self._data = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {CONF_NAME: user_input[CONF_NAME]}
            return await self.async_step_telegram()
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_telegram(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_voice()
        return self.async_show_form(
            step_id="telegram",
            data_schema=STEP_TELEGRAM_SCHEMA,
        )

    async def async_step_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_settings()
        return self.async_show_form(
            step_id="voice",
            data_schema=STEP_VOICE_SCHEMA,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )
        return self.async_show_form(
            step_id="settings",
            data_schema=STEP_SETTINGS_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return ATCOptionsFlow(config_entry)


class ATCOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ATC."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = dict(self._config_entry.options or self._config_entry.data)
        schema = vol.Schema({
            vol.Optional(CONF_NAME, default=current.get(CONF_NAME, "ATC")): str,
            vol.Optional("telegram_mode", default=current.get("telegram_mode", TelegramMode.NONE)): vol.In([m.value for m in TelegramMode]),
            vol.Optional("telegram_bot_token", default=current.get("telegram_bot_token", "")): str,
            vol.Optional("telegram_chat_id", default=current.get("telegram_chat_id", "")): str,
            vol.Optional("telegram_notify_service", default=current.get("telegram_notify_service", "")): str,
            vol.Optional("voice_provider", default=current.get("voice_provider", VoiceProvider.NONE)): vol.In([p.value for p in VoiceProvider]),
            vol.Optional("voice_media_player", default=current.get("voice_media_player", "")): str,
            vol.Optional("voice_volume", default=current.get("voice_volume", 0.5)): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            vol.Optional("voice_tts_engine", default=current.get("voice_tts_engine", "")): str,
            vol.Optional("voice_language", default=current.get("voice_language", "")): str,
            vol.Optional("default_reminder_minutes", default=current.get("default_reminder_minutes", 30)): vol.All(vol.Coerce(int), vol.Range(min=1, max=10080)),
            vol.Optional("timezone", default=current.get("timezone", "")): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
