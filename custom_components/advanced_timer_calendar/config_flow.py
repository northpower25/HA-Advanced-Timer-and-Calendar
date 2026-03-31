"""Config flow for HA Advanced Timer & Calendar."""
from __future__ import annotations
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN, TelegramMode, VoiceProvider


# ---------------------------------------------------------------------------
# Helpers shared by config flow and options flow
# ---------------------------------------------------------------------------

def _list_telegram_notify_services(hass: HomeAssistant) -> list[str]:
    """Return notify service names that belong to a Telegram bot."""
    notify = hass.services.async_services().get("notify", {})
    return sorted(k for k in notify if "telegram" in k.lower())


def _list_telegram_bot_entries(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return configured telegram_bot integration config entries as {value, label} dicts."""
    entries = hass.config_entries.async_entries("telegram_bot")
    return [{"value": e.entry_id, "label": e.title} for e in entries]


def _list_tts_services(hass: HomeAssistant) -> list[str]:
    """Return available TTS services as 'tts.<service>' strings."""
    tts = hass.services.async_services().get("tts", {})
    return sorted(f"tts.{svc}" for svc in tts.keys())


def _make_voice_config_schema(
    provider: str,
    tts_services: list[str],
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build a provider-specific voice configuration schema."""
    if defaults is None:
        defaults = {}

    # Normalise existing value – may be a legacy comma-separated string
    existing_players: list[str] | str = defaults.get("voice_media_player", [])
    if isinstance(existing_players, str):
        existing_players = [e.strip() for e in existing_players.split(",") if e.strip()]

    media_player_field: Any
    if existing_players:
        media_player_field = vol.Required("voice_media_player", default=existing_players)
    else:
        media_player_field = vol.Required("voice_media_player")

    fields: dict = {
        media_player_field: EntitySelector(
            EntitySelectorConfig(domain="media_player", multiple=True)
        ),
        vol.Optional(
            "voice_volume", default=defaults.get("voice_volume", 0.5)
        ): NumberSelector(
            NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode=NumberSelectorMode.SLIDER)
        ),
    }

    if provider in (
        VoiceProvider.GOOGLE_CAST,
        VoiceProvider.SONOS,
        VoiceProvider.GENERIC_TTS,
    ):
        default_tts = defaults.get("voice_tts_engine", "")
        if tts_services:
            if default_tts not in tts_services:
                default_tts = tts_services[0]
            fields[vol.Optional("voice_tts_engine", default=default_tts)] = SelectSelector(
                SelectSelectorConfig(
                    options=tts_services,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            fields[vol.Optional("voice_tts_engine", default=default_tts)] = str
        fields[vol.Optional("voice_language", default=defaults.get("voice_language", ""))] = str

    return vol.Schema(fields)


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------

class ATCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle configuration flow for ATC."""

    VERSION = 1
    _data: dict[str, Any]

    def __init__(self) -> None:
        self._data = {}

    # ── Step 1: Instance name ─────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {CONF_NAME: user_input[CONF_NAME]}
            return await self.async_step_telegram()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default="ATC"): str}),
            errors=errors,
        )

    # ── Step 2: Telegram – mode selection ─────────────────────────────────────

    async def async_step_telegram(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            mode = user_input.get("telegram_mode", TelegramMode.NONE)
            self._data["telegram_mode"] = mode
            if mode == TelegramMode.MODE_A:
                return await self.async_step_telegram_direct()
            if mode == TelegramMode.MODE_B:
                return await self.async_step_telegram_ha()
            return await self.async_step_voice()
        return self.async_show_form(
            step_id="telegram",
            data_schema=vol.Schema({
                vol.Required(
                    "telegram_mode", default=TelegramMode.NONE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[m.value for m in TelegramMode],
                        translation_key="telegram_mode",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ── Step 2a: Direct Telegram Bot (own token + chat ID) ────────────────────

    async def async_step_telegram_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_voice()
        return self.async_show_form(
            step_id="telegram_direct",
            data_schema=vol.Schema({
                vol.Required("telegram_bot_token"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required("telegram_chat_id"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
        )

    # ── Step 2b: Telegram via HA telegram_bot integration ─────────────────────

    async def async_step_telegram_ha(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_voice()

        bot_entries = _list_telegram_bot_entries(self.hass)
        fields: dict = {}
        if bot_entries:
            fields[vol.Optional("telegram_bot_entry_id", default=bot_entries[0]["value"])] = SelectSelector(
                SelectSelectorConfig(
                    options=bot_entries,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback: list notify services or free-text entry
            notify_services = _list_telegram_notify_services(self.hass)
            if notify_services:
                fields[vol.Optional("telegram_notify_service", default="")] = SelectSelector(
                    SelectSelectorConfig(options=notify_services, mode=SelectSelectorMode.DROPDOWN)
                )

        fields[vol.Required("telegram_chat_id")] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        return self.async_show_form(
            step_id="telegram_ha",
            data_schema=vol.Schema(fields),
            errors={},
            description_placeholders={"bot_count": str(len(bot_entries))},
        )

    # ── Step 3: Voice – provider selection ────────────────────────────────────

    async def async_step_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            provider = user_input.get("voice_provider", VoiceProvider.NONE)
            self._data["voice_provider"] = provider
            if provider != VoiceProvider.NONE:
                return await self.async_step_voice_config()
            return await self.async_step_calendar_sync()
        return self.async_show_form(
            step_id="voice",
            data_schema=vol.Schema({
                vol.Required(
                    "voice_provider", default=VoiceProvider.NONE
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[p.value for p in VoiceProvider],
                        translation_key="voice_provider",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ── Step 3a: Voice – provider-specific configuration ──────────────────────

    async def async_step_voice_config(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        provider = self._data.get("voice_provider", VoiceProvider.NONE)
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_calendar_sync()
        tts_services = _list_tts_services(self.hass)
        return self.async_show_form(
            step_id="voice_config",
            data_schema=_make_voice_config_schema(provider, tts_services),
        )

    # ── Step 4: Calendar sync – provider selection ────────────────────────────

    async def async_step_calendar_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            sync_provider = user_input.get("calendar_sync_provider", "none")
            self._data["calendar_sync_provider"] = sync_provider
            if sync_provider == "google":
                return await self.async_step_calendar_google()
            if sync_provider == "microsoft":
                return await self.async_step_calendar_microsoft()
            return await self.async_step_settings()
        return self.async_show_form(
            step_id="calendar_sync",
            data_schema=vol.Schema({
                vol.Required(
                    "calendar_sync_provider", default="none"
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=["none", "google", "microsoft"],
                        translation_key="calendar_sync_provider",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ── Step 4a: Google Calendar credentials ──────────────────────────────────

    async def async_step_calendar_google(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("google_client_id") or not user_input.get("google_client_secret"):
                errors["base"] = "credentials_required"
            else:
                self._data.update(user_input)
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="calendar_google",
            data_schema=vol.Schema({
                vol.Required("google_client_id"): str,
                vol.Required("google_client_secret"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
        )

    # ── Step 4b: Microsoft 365 credentials ────────────────────────────────────

    async def async_step_calendar_microsoft(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("ms_client_id") or not user_input.get("ms_client_secret"):
                errors["base"] = "credentials_required"
            else:
                self._data.update(user_input)
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="calendar_microsoft",
            data_schema=vol.Schema({
                vol.Required("ms_client_id"): str,
                vol.Required("ms_client_secret"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional("ms_tenant_id", default="common"): str,
            }),
            errors=errors,
        )

    # ── Step 5: Default settings ───────────────────────────────────────────────

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data.update(user_input)
            title = self._data.get(CONF_NAME, "ATC")
            return self.async_create_entry(title=title, data=self._data)
        try:
            default_minutes = int(self._data.get("default_reminder_minutes", 30) or 30)
        except (ValueError, TypeError):
            default_minutes = 30
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional("default_reminder_minutes", default=default_minutes): NumberSelector(
                    NumberSelectorConfig(min=1, max=10080, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional("timezone", default=""): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return ATCOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------

class ATCOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for ATC."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        # Seed with all existing values so untouched settings are preserved.
        self._options: dict[str, Any] = dict(
            config_entry.options or config_entry.data
        )

    def _current(self) -> dict[str, Any]:
        return self._options

    # ── init → telegram ────────────────────────────────────────────────────────

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        return await self.async_step_telegram()

    # ── Telegram mode ──────────────────────────────────────────────────────────

    async def async_step_telegram(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            mode = user_input.get("telegram_mode", TelegramMode.NONE)
            self._options["telegram_mode"] = mode
            if mode == TelegramMode.MODE_A:
                return await self.async_step_telegram_direct()
            if mode == TelegramMode.MODE_B:
                return await self.async_step_telegram_ha()
            return await self.async_step_voice()
        return self.async_show_form(
            step_id="telegram",
            data_schema=vol.Schema({
                vol.Required(
                    "telegram_mode",
                    default=current.get("telegram_mode", TelegramMode.NONE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[m.value for m in TelegramMode],
                        translation_key="telegram_mode",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_telegram_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_voice()
        return self.async_show_form(
            step_id="telegram_direct",
            data_schema=vol.Schema({
                vol.Required(
                    "telegram_bot_token",
                    default=current.get("telegram_bot_token", ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Required(
                    "telegram_chat_id",
                    default=current.get("telegram_chat_id", ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            }),
        )

    async def async_step_telegram_ha(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_voice()

        bot_entries = _list_telegram_bot_entries(self.hass)
        fields: dict = {}
        if bot_entries:
            current_entry = current.get("telegram_bot_entry_id", bot_entries[0]["value"])
            fields[vol.Optional("telegram_bot_entry_id", default=current_entry)] = SelectSelector(
                SelectSelectorConfig(
                    options=bot_entries,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            notify_services = _list_telegram_notify_services(self.hass)
            if notify_services:
                fields[vol.Optional("telegram_notify_service", default=current.get("telegram_notify_service", ""))] = SelectSelector(
                    SelectSelectorConfig(options=notify_services, mode=SelectSelectorMode.DROPDOWN)
                )

        fields[vol.Required("telegram_chat_id", default=current.get("telegram_chat_id", ""))] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        return self.async_show_form(
            step_id="telegram_ha",
            data_schema=vol.Schema(fields),
            errors={},
            description_placeholders={"bot_count": str(len(bot_entries))},
        )

    # ── Voice provider ─────────────────────────────────────────────────────────

    async def async_step_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            provider = user_input.get("voice_provider", VoiceProvider.NONE)
            self._options["voice_provider"] = provider
            if provider != VoiceProvider.NONE:
                return await self.async_step_voice_config()
            return await self.async_step_calendar_sync()
        return self.async_show_form(
            step_id="voice",
            data_schema=vol.Schema({
                vol.Required(
                    "voice_provider",
                    default=current.get("voice_provider", VoiceProvider.NONE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[p.value for p in VoiceProvider],
                        translation_key="voice_provider",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_voice_config(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        provider = self._options.get("voice_provider", VoiceProvider.NONE)
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_calendar_sync()
        tts_services = _list_tts_services(self.hass)
        return self.async_show_form(
            step_id="voice_config",
            data_schema=_make_voice_config_schema(provider, tts_services, defaults=current),
        )

    # ── Calendar sync ──────────────────────────────────────────────────────────

    async def async_step_calendar_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        if user_input is not None:
            sync_provider = user_input.get("calendar_sync_provider", "none")
            self._options["calendar_sync_provider"] = sync_provider
            if sync_provider == "google":
                return await self.async_step_calendar_google()
            if sync_provider == "microsoft":
                return await self.async_step_calendar_microsoft()
            return await self.async_step_settings()
        return self.async_show_form(
            step_id="calendar_sync",
            data_schema=vol.Schema({
                vol.Required(
                    "calendar_sync_provider",
                    default=current.get("calendar_sync_provider", "none"),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=["none", "google", "microsoft"],
                        translation_key="calendar_sync_provider",
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_calendar_google(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("google_client_id") or not user_input.get("google_client_secret"):
                errors["base"] = "credentials_required"
            else:
                self._options.update(user_input)
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="calendar_google",
            data_schema=vol.Schema({
                vol.Required(
                    "google_client_id",
                    default=current.get("google_client_id", ""),
                ): str,
                vol.Required(
                    "google_client_secret",
                    default=current.get("google_client_secret", ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            }),
            errors=errors,
        )

    async def async_step_calendar_microsoft(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("ms_client_id") or not user_input.get("ms_client_secret"):
                errors["base"] = "credentials_required"
            else:
                self._options.update(user_input)
                return await self.async_step_settings()
        return self.async_show_form(
            step_id="calendar_microsoft",
            data_schema=vol.Schema({
                vol.Required(
                    "ms_client_id",
                    default=current.get("ms_client_id", ""),
                ): str,
                vol.Required(
                    "ms_client_secret",
                    default=current.get("ms_client_secret", ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Optional(
                    "ms_tenant_id",
                    default=current.get("ms_tenant_id", "common"),
                ): str,
            }),
            errors=errors,
        )

    # ── Default settings ───────────────────────────────────────────────────────

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        current = self._current()
        errors: dict[str, str] = {}
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)
        try:
            default_minutes = int(current.get("default_reminder_minutes", 30) or 30)
        except (ValueError, TypeError):
            default_minutes = 30
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional(
                    "default_reminder_minutes",
                    default=default_minutes,
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=10080, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    "timezone", default=current.get("timezone") or ""
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
            }),
            errors=errors,
        )
