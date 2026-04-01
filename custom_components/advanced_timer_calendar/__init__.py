"""HA Advanced Timer & Calendar integration."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PLATFORMS, SyncDirection, ConflictStrategy
from .coordinator import ATCDataCoordinator
from .scheduler import ATCScheduler
from .services import async_register_services
from .storage import ATCStorage

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

        try:
            from homeassistant.components.frontend import add_extra_js_url
            for card_file in _CARD_FILES:
                if (card_dir / card_file).exists():
                    card_url = f"/{DOMAIN}_local/{card_file}?v={_CARD_VERSION}"
                    add_extra_js_url(hass, card_url)
                    _LOGGER.debug("ATC card registered: %s", card_url)
        except ImportError:
            # Fallback for older HA versions
            for card_file in _CARD_FILES:
                if (card_dir / card_file).exists():
                    card_url = f"/{DOMAIN}_local/{card_file}?v={_CARD_VERSION}"
                    hass.data.setdefault("frontend_extra_module_url", set()).add(card_url)
                    _LOGGER.debug("ATC card registered (fallback): %s", card_url)

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

        # Register the YAML dashboard with HA's Lovelace component.
        # This is done here and also deferred to EVENT_HOMEASSISTANT_STARTED
        # to handle cases where the lovelace component initialises after us.
        _register_lovelace_yaml(hass, dashboard_yaml)

        @callback
        def _on_ha_started(_event: Any) -> None:
            """Re-register the Lovelace YAML dashboard after HA has started."""
            _register_lovelace_yaml(hass, dashboard_yaml)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_ha_started)

        _LOGGER.info("ATC Lovelace panel registered at /%s", _PANEL_URL_PATH)

    except (ImportError, ValueError, TypeError) as err:  # noqa: BLE001
        _LOGGER.error("Failed to register ATC Lovelace panel: %s", err, exc_info=True)


def _register_lovelace_yaml(hass: HomeAssistant, dashboard_yaml: Path) -> None:
    """Register (or re-register) the LovelaceYAML dashboard entry."""
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
                "Lovelace data not available; ATC dashboard content may not "
                "load.  Ensure 'lovelace' is listed in the integration dependencies."
            )
    except (ImportError, AttributeError) as inner_err:
        _LOGGER.warning("Could not register Lovelace YAML dashboard: %s", inner_err)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the ATC component (called once for the domain)."""
    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend_cards(hass)
    await _async_register_lovelace_panel(hass)
    return True


async def _async_provision_calendar_account(
    coordinator: ATCDataCoordinator,
    entry: ConfigEntry,
) -> None:
    """Create or update a calendar_accounts storage record from config-entry credentials.

    When a user configures a Microsoft or Google calendar in the Setup/Options
    flow, the credentials land in ``entry.data`` / ``entry.options``.  They are
    NOT automatically mirrored into the ``calendar_accounts`` storage list that
    the sync engine, sensor platform, and dashboard card all read from.  This
    function bridges that gap: it creates the account record on first run and
    keeps the credentials in sync whenever the options flow saves new values.
    """
    # Effective config: options override data (same behaviour as HA convention)
    cfg: dict[str, Any] = {**entry.data, **(entry.options or {})}
    provider: str = cfg.get("calendar_sync_provider", "none")
    if provider not in ("microsoft", "google"):
        return

    if provider == "microsoft":
        client_id = cfg.get("ms_client_id", "")
        client_secret = cfg.get("ms_client_secret", "")
        tenant_id = cfg.get("ms_tenant_id", "common")  # "common" works for both personal and multi-tenant apps
        display_name = "Microsoft 365"
        extra: dict[str, Any] = {"tenant_id": tenant_id}
    else:  # google
        client_id = cfg.get("google_client_id", "")
        client_secret = cfg.get("google_client_secret", "")
        display_name = "Google Calendar"
        extra = {}

    if not client_id or not client_secret:
        _LOGGER.warning(
            "ATC: calendar provider '%s' is configured but credentials are incomplete "
            "(client_id or client_secret missing) – skipping account provisioning.",
            provider,
        )
        return

    data = await coordinator.storage.async_load()
    accounts: list[dict[str, Any]] = data.setdefault("calendar_accounts", [])

    # Look for an existing account that was provisioned from the same provider
    # and client_id so we can update credentials instead of creating duplicates.
    existing = next(
        (a for a in accounts if a.get("provider") == provider and a.get("client_id") == client_id),
        None,
    )
    if existing is not None:
        # Update mutable credential fields in case the user changed them via options flow.
        # The display name is intentionally left unchanged so users can rename the account
        # via the dashboard without having it overwritten on every HA restart.
        existing["client_secret"] = client_secret
        existing.update(extra)
    else:
        account: dict[str, Any] = {
            "id": ATCStorage.new_id(),
            "name": display_name,
            "provider": provider,
            "client_id": client_id,
            "client_secret": client_secret,
            "sync_direction": SyncDirection.BIDIRECTIONAL,
            "conflict_strategy": ConflictStrategy.NEWEST_WINS,
            "calendars": [],
            "sync_status": "idle",
            "last_sync": None,
            "access_token": None,
            "refresh_token": None,
            "token_expiry": None,
        }
        account.update(extra)
        accounts.append(account)
        _LOGGER.info(
            "ATC: created calendar account '%s' (%s) from config-entry credentials",
            display_name,
            provider,
        )

    await coordinator.storage.async_save(data)
    await coordinator.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ATCDataCoordinator(hass, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()

    await _async_provision_calendar_account(coordinator, entry)

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
    domain_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator: ATCDataCoordinator | None = domain_data.get("coordinator")
    if coordinator is not None:
        await _async_provision_calendar_account(coordinator, entry)
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
