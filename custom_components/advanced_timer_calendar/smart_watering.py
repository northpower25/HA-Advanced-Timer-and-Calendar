"""Smart Watering – adaptive irrigation duration calculation."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class WateringProfile:
    """Configuration for a smart watering profile."""
    timer_id: str
    base_duration_seconds: int = 600          # 10 min default
    temperature_sensor: str | None = None
    soil_moisture_sensor: str | None = None
    weather_entity: str | None = None
    # Thresholds
    temperature_high: float = 30.0            # °C – increase watering
    temperature_low: float = 10.0             # °C – decrease watering
    soil_moisture_target: float = 50.0        # % – skip if above
    rain_probability_threshold: float = 0.6   # skip if rain expected
    # Adjustment factors
    factor_hot: float = 1.5                   # × base when temp > temperature_high
    factor_cold: float = 0.5                  # × base when temp < temperature_low
    factor_dry: float = 1.3                   # × base when soil very dry
    enabled: bool = True


class SmartWateringAlgorithm:
    """Calculate optimal watering duration and decide whether to skip."""

    def __init__(self, hass: "HomeAssistant") -> None:
        self.hass = hass

    def calculate_duration(self, profile: WateringProfile) -> int:
        """Return adjusted duration in seconds (0 = skip entirely)."""
        if not profile.enabled:
            return profile.base_duration_seconds

        factor = 1.0

        # --- Weather forecast ---
        if profile.weather_entity:
            try:
                weather_state = self.hass.states.get(profile.weather_entity)
                if weather_state:
                    # Many HA weather entities expose forecast in attributes
                    forecast = weather_state.attributes.get("forecast", [])
                    if forecast:
                        rain_prob = forecast[0].get("precipitation_probability", 0) / 100
                        if rain_prob >= profile.rain_probability_threshold:
                            _LOGGER.info(
                                "Smart watering: skipping – rain probability %.0f%%",
                                rain_prob * 100,
                            )
                            return 0
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Weather lookup failed: %s", exc)

        # --- Temperature ---
        if profile.temperature_sensor:
            try:
                temp_state = self.hass.states.get(profile.temperature_sensor)
                if temp_state and temp_state.state not in ("unknown", "unavailable"):
                    temp = float(temp_state.state)
                    if temp > profile.temperature_high:
                        factor *= profile.factor_hot
                    elif temp < profile.temperature_low:
                        factor *= profile.factor_cold
            except (ValueError, TypeError) as exc:
                _LOGGER.debug("Temperature read failed: %s", exc)

        # --- Soil moisture ---
        if profile.soil_moisture_sensor:
            try:
                moisture_state = self.hass.states.get(profile.soil_moisture_sensor)
                if moisture_state and moisture_state.state not in ("unknown", "unavailable"):
                    moisture = float(moisture_state.state)
                    if moisture >= profile.soil_moisture_target:
                        _LOGGER.info(
                            "Smart watering: skipping – soil moisture %.1f%% >= target %.1f%%",
                            moisture,
                            profile.soil_moisture_target,
                        )
                        return 0
                    if moisture < profile.soil_moisture_target * 0.5:
                        factor *= profile.factor_dry
            except (ValueError, TypeError) as exc:
                _LOGGER.debug("Soil moisture read failed: %s", exc)

        adjusted = int(profile.base_duration_seconds * factor)
        _LOGGER.debug(
            "Smart watering: base=%ds factor=%.2f adjusted=%ds",
            profile.base_duration_seconds,
            factor,
            adjusted,
        )
        return max(60, adjusted)  # minimum 1 minute

    def should_skip(self, profile: WateringProfile) -> bool:
        """Return True if watering should be skipped entirely."""
        return self.calculate_duration(profile) == 0

    @staticmethod
    def profile_from_dict(data: dict) -> WateringProfile:
        return WateringProfile(
            timer_id=data["timer_id"],
            base_duration_seconds=data.get("base_duration_seconds", 600),
            temperature_sensor=data.get("temperature_sensor"),
            soil_moisture_sensor=data.get("soil_moisture_sensor"),
            weather_entity=data.get("weather_entity"),
            temperature_high=data.get("temperature_high", 30.0),
            temperature_low=data.get("temperature_low", 10.0),
            soil_moisture_target=data.get("soil_moisture_target", 50.0),
            rain_probability_threshold=data.get("rain_probability_threshold", 0.6),
            factor_hot=data.get("factor_hot", 1.5),
            factor_cold=data.get("factor_cold", 0.5),
            factor_dry=data.get("factor_dry", 1.3),
            enabled=data.get("enabled", True),
        )

    @staticmethod
    def profile_to_dict(profile: WateringProfile) -> dict:
        return {
            "timer_id": profile.timer_id,
            "base_duration_seconds": profile.base_duration_seconds,
            "temperature_sensor": profile.temperature_sensor,
            "soil_moisture_sensor": profile.soil_moisture_sensor,
            "weather_entity": profile.weather_entity,
            "temperature_high": profile.temperature_high,
            "temperature_low": profile.temperature_low,
            "soil_moisture_target": profile.soil_moisture_target,
            "rain_probability_threshold": profile.rain_probability_threshold,
            "factor_hot": profile.factor_hot,
            "factor_cold": profile.factor_cold,
            "factor_dry": profile.factor_dry,
            "enabled": profile.enabled,
        }
