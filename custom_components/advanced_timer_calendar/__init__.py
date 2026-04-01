"""HA Advanced Timer & Calendar integration."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import ATCDataCoordinator
from .scheduler import ATCScheduler
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

type ATCConfigEntry = ConfigEntry

# Frontend card configuration
_CARD_VERSION = "1.0.0"
_CARD_FILES = [
    "atc-timer-card.js",
    "atc-reminder-card.js",
    "atc-status-card.js",
]

# Dashboard panel configuration
_PANEL_URL_PATH = "atc-dashboard"
_PANEL_TITLE = "ATC Dashboard"
_PANEL_ICON = "mdi:timer-outline"


async def _async_register_frontend_cards(hass: HomeAssistant) -> None:
    """Register ATC custom Lovelace cards as frontend resources.

    The card JS files are served from the integration's own www/ directory so
    no manual file-copying to /config/www is required.
    """
    try:
        from homeassistant.components.http import StaticPathConfig

        card_dir = Path(__file__).parent / "www"
        if not card_dir.exists():
            _LOGGER.warning("ATC www directory not found at %s – cards will not be available", card_dir)
            return

        await hass.http.async_register_static_paths([
            StaticPathConfig(
                url_path=f"/{DOMAIN}_local",
                path=str(card_dir),
                cache_headers=False,
            )
        ])

        for card_file in _CARD_FILES:
            if (card_dir / card_file).exists():
                card_url = f"/{DOMAIN}_local/{card_file}?v={_CARD_VERSION}"
                hass.data.setdefault("frontend_extra_module_url", set()).add(card_url)
                _LOGGER.debug("ATC card registered: %s", card_url)

        _LOGGER.info("ATC frontend cards registered from %s", card_dir)

    except (ImportError, OSError, ValueError) as err:  # noqa: BLE001
        _LOGGER.error("Failed to register ATC frontend cards: %s", err, exc_info=True)


async def _async_register_lovelace_panel(hass: HomeAssistant) -> None:
    """Register the ATC dashboard as a Lovelace sidebar panel.

    The dashboard YAML is read from the integration's own directory so no
    manual copy-paste into the Lovelace raw editor is required.
    """
    try:
        from homeassistant.components.frontend import async_register_built_in_panel

        dashboard_yaml = Path(__file__).parent / "dashboard.yaml"
        if not dashboard_yaml.exists():
            _LOGGER.warning("ATC dashboard.yaml not found at %s – panel will not be registered", dashboard_yaml)
            return

        # Register the sidebar panel entry.  The config dict must only contain
        # {"mode": "yaml"} – the "filename" key is not part of the panel config
        # and is ignored by the frontend.
        async_register_built_in_panel(
            hass,
            "lovelace",
            sidebar_title=_PANEL_TITLE,
            sidebar_icon=_PANEL_ICON,
            frontend_url_path=_PANEL_URL_PATH,
            config={"mode": "yaml"},
            require_admin=False,
        )

        # Also register the YAML dashboard with HA's Lovelace component so that
        # the WebSocket "lovelace/config" command can find and serve the content.
        # Without this step the panel is shown but hass.data[LOVELACE_DATA].dashboards
        # has no entry for _PANEL_URL_PATH and the frontend falls back to an
        # empty auto-generated view ("Neuer Abschnitt").
        try:
            from homeassistant.components.lovelace.const import LOVELACE_DATA
            from homeassistant.components.lovelace.dashboard import LovelaceYAML
            from homeassistant.const import CONF_FILENAME

            lovelace = hass.data.get(LOVELACE_DATA)
            if lovelace is not None:
                if _PANEL_URL_PATH not in lovelace.dashboards:
                    lovelace.dashboards[_PANEL_URL_PATH] = LovelaceYAML(
                        hass,
                        _PANEL_URL_PATH,
                        {CONF_FILENAME: str(dashboard_yaml)},
                    )
                    _LOGGER.debug("ATC Lovelace YAML dashboard registered for /%s", _PANEL_URL_PATH)
                else:
                    _LOGGER.debug(
                        "ATC Lovelace YAML dashboard already registered for /%s – skipping",
                        _PANEL_URL_PATH,
                    )
            else:
                _LOGGER.warning(
                    "Lovelace data not available yet; ATC dashboard content may not "
                    "load.  Ensure 'lovelace' is listed in the integration dependencies."
                )
        except (ImportError, AttributeError) as inner_err:
            _LOGGER.warning("Could not register Lovelace YAML dashboard: %s", inner_err)

        _LOGGER.info("ATC Lovelace panel registered at /%s", _PANEL_URL_PATH)

    except (ImportError, ValueError, TypeError) as err:  # noqa: BLE001
        _LOGGER.error("Failed to register ATC Lovelace panel: %s", err, exc_info=True)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the ATC component (called once for the domain)."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend_cards(hass)
    await _async_register_lovelace_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ATCDataCoordinator(hass, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    scheduler = ATCScheduler(hass, coordinator)
    await scheduler.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "scheduler": scheduler,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data[DOMAIN].get(entry.entry_id, {})
    scheduler: ATCScheduler | None = domain_data.get("scheduler")
    if scheduler:
        scheduler.cancel_all()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
