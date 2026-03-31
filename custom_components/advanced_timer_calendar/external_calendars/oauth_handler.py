"""OAuth 2.0 handler for external calendar providers."""
from __future__ import annotations
import logging
from typing import Any
from urllib.parse import urlencode

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)


class OAuthHandler:
    """Handles OAuth 2.0 flows for external calendar providers."""

    def __init__(self, hass: HomeAssistant, account: dict[str, Any]) -> None:
        self.hass = hass
        self.account = account

    def get_authorization_url(
        self,
        auth_endpoint: str,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str = "",
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Build an OAuth 2.0 authorization URL."""
        params: dict[str, str] = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope,
        }
        if state:
            params["state"] = state
        if extra_params:
            params.update(extra_params)
        return f"{auth_endpoint}?{urlencode(params)}"

    async def async_exchange_code(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Exchange an authorization code for tokens."""
        session = async_get_clientsession(self.hass)
        payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if extra_params:
            payload.update(extra_params)
        try:
            async with session.post(
                token_endpoint, data=payload, timeout=15
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                _LOGGER.warning("Token exchange failed %s: %s", resp.status, body)
        except Exception as exc:
            _LOGGER.error("Token exchange error: %s", exc)
        return None

    async def async_refresh_access_token(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Use a refresh token to obtain a new access token."""
        session = async_get_clientsession(self.hass)
        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }
        if extra_params:
            payload.update(extra_params)
        try:
            async with session.post(
                token_endpoint, data=payload, timeout=15
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                _LOGGER.warning("Token refresh failed %s: %s", resp.status, body)
        except Exception as exc:
            _LOGGER.error("Token refresh error: %s", exc)
        return None

    def store_tokens(
        self,
        token_data: dict[str, Any],
        expires_in_key: str = "expires_in",
    ) -> None:
        """Store access/refresh tokens in the account dict."""
        self.account["access_token"] = token_data.get("access_token")
        if "refresh_token" in token_data:
            self.account["refresh_token"] = token_data["refresh_token"]
        expires_in = token_data.get(expires_in_key, 3600)
        expiry = dt_util.utcnow() + timedelta(seconds=int(expires_in) - 60)
        self.account["token_expiry"] = expiry.isoformat()

    async def async_client_credentials_token(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        scope: str,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Obtain an access token via client credentials flow."""
        session = async_get_clientsession(self.hass)
        payload: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        }
        if extra_params:
            payload.update(extra_params)
        try:
            async with session.post(
                token_endpoint, data=payload, timeout=15
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                body = await resp.text()
                _LOGGER.warning("Client credentials token failed %s: %s", resp.status, body)
        except Exception as exc:
            _LOGGER.error("Client credentials token error: %s", exc)
        return None
