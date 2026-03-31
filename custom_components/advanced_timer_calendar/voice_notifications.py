"""Voice notification support for HA Advanced Timer & Calendar."""
from __future__ import annotations
import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import VoiceProvider

_LOGGER = logging.getLogger(__name__)


class ATCVoiceNotifier:
    """Sends voice announcements via Alexa, Google Cast, Sonos, or generic TTS."""

    @staticmethod
    async def async_announce(
        hass: HomeAssistant,
        message: str,
        config: dict[str, Any],
    ) -> None:
        """Announce a message on the configured voice device(s)."""
        provider = config.get("voice_provider", VoiceProvider.NONE)
        if provider == VoiceProvider.NONE:
            return

        media_players = config.get("voice_media_player", [])
        if not media_players:
            _LOGGER.warning("No voice media player configured.")
            return

        # Support both a list (from entity selector) and a legacy comma-separated string
        if isinstance(media_players, list):
            entity_ids = [e for e in media_players if e]
        else:
            entity_ids = [e.strip() for e in media_players.split(",") if e.strip()]
        volume = config.get("voice_volume", 0.5)
        tts_engine = config.get("voice_tts_engine", "tts.cloud_say")
        language = config.get("voice_language", "")

        for entity_id in entity_ids:
            try:
                if provider == VoiceProvider.ALEXA:
                    await ATCVoiceNotifier._announce_alexa(hass, entity_id, message, volume)
                elif provider in (VoiceProvider.GOOGLE_CAST, VoiceProvider.SONOS, VoiceProvider.GENERIC_TTS):
                    await ATCVoiceNotifier._announce_tts(
                        hass, entity_id, message, volume, tts_engine, language
                    )
            except Exception as exc:
                _LOGGER.error("Voice announcement error for %s: %s", entity_id, exc)

    @staticmethod
    async def _get_current_volume(hass: HomeAssistant, entity_id: str) -> float | None:
        """Get the current volume level of a media player entity."""
        state = hass.states.get(entity_id)
        if state is None:
            return None
        try:
            return float(state.attributes.get("volume_level", 0.5))
        except (TypeError, ValueError):
            return None

    @staticmethod
    async def _set_volume(
        hass: HomeAssistant, entity_id: str, volume: float
    ) -> None:
        """Set the volume level of a media player."""
        try:
            await hass.services.async_call(
                "media_player",
                "volume_set",
                {"entity_id": entity_id, "volume_level": volume},
                blocking=True,
            )
        except Exception as exc:
            _LOGGER.warning("Volume set error for %s: %s", entity_id, exc)

    @staticmethod
    async def _announce_alexa(
        hass: HomeAssistant,
        entity_id: str,
        message: str,
        volume: float,
    ) -> None:
        """Announce via Alexa Media Player integration."""
        original_volume = await ATCVoiceNotifier._get_current_volume(hass, entity_id)

        if original_volume is not None:
            await ATCVoiceNotifier._set_volume(hass, entity_id, volume)

        try:
            # Derive the notify service name from the entity_id
            # entity_id: media_player.alexa_kitchen -> notify.alexa_media_kitchen
            device_name = entity_id.replace("media_player.", "").replace(".", "_")
            notify_service = f"alexa_media_{device_name}"
            await hass.services.async_call(
                "notify",
                notify_service,
                {
                    "message": message,
                    "data": {"type": "announce"},
                },
                blocking=False,
            )
        except Exception as exc:
            _LOGGER.warning("Alexa announce error for %s: %s", entity_id, exc)
        finally:
            if original_volume is not None:
                await asyncio.sleep(3)
                await ATCVoiceNotifier._set_volume(hass, entity_id, original_volume)

    @staticmethod
    async def _announce_tts(
        hass: HomeAssistant,
        entity_id: str,
        message: str,
        volume: float,
        tts_engine: str,
        language: str,
    ) -> None:
        """Announce via TTS speak service (Google Cast, Sonos, generic)."""
        original_volume = await ATCVoiceNotifier._get_current_volume(hass, entity_id)

        if original_volume is not None:
            await ATCVoiceNotifier._set_volume(hass, entity_id, volume)

        try:
            tts_parts = tts_engine.split(".", 1)
            tts_domain = tts_parts[0] if len(tts_parts) == 2 else "tts"
            tts_service = tts_parts[1] if len(tts_parts) == 2 else tts_engine

            service_data: dict[str, Any] = {
                "entity_id": entity_id,
                "message": message,
            }
            if language:
                service_data["language"] = language

            await hass.services.async_call(
                tts_domain,
                tts_service,
                service_data,
                blocking=False,
            )
        except Exception as exc:
            _LOGGER.warning("TTS announce error for %s: %s", entity_id, exc)
        finally:
            if original_volume is not None:
                await asyncio.sleep(5)
                await ATCVoiceNotifier._set_volume(hass, entity_id, original_volume)
