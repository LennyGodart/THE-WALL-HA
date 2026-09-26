"""Config flow for THE WALL.

Pairing works like on a TV remote: Home Assistant asks the server for a code,
the panel shows it, and the user types it in. One config entry is one device.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_CODE, CONF_DEVICE_ID
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api import (
    TheWallApiError,
    TheWallClient,
    TheWallConnectionError,
    TheWallRateLimitError,
    normalize_code,
    normalize_server,
    normalize_uid,
)
from .const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_UID,
    DEFAULT_SERVER,
    DOMAIN,
    LOGGER,
    PAIRING_NAME,
    ZEROCONF_TYPE,
)

# /pair errors shown as they are.
_PAIR_ERRORS = {"device_offline", "unknown_device"}
# The pairing is gone: the code expired, or the server no longer knows it.
_GONE_ERRORS = {"pairing_expired", "unknown_pairing"}

STEP_PAIR_SCHEMA = vol.Schema({vol.Required(CONF_CODE): TextSelector()})


class TheWallConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one THE WALL with the code from its panel."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Start empty."""
        self._uid = ""
        self._server = DEFAULT_SERVER
        self._name = ""
        self._pairing = ""
        self._length = 6
        self._attempts_left = ""

    def _client(self) -> TheWallClient:
        """Return a client without token, pairing needs none."""
        return TheWallClient(async_get_clientsession(self.hass), self._server)

    def _placeholders(self) -> dict[str, str]:
        return {
            "name": self._name or self._uid,
            "uid": self._uid,
            "server": self._server,
            "length": str(self._length),
            "attempts_left": self._attempts_left,
        }

    async def _async_request_code(self) -> dict[str, str]:
        """Ask the server to show a code. Returns form errors, empty on success."""
        try:
            result = await self._client().pair(self._uid)
        except TheWallRateLimitError:
            return {"base": "rate_limited"}
        except TheWallApiError as err:
            if err.code in _PAIR_ERRORS:
                return {"base": err.code}
            if err.code == "bad_request":
                return {"base": "invalid_device_id"}
            LOGGER.warning("Pairing with %s failed: %s", self._uid, err)
            return {"base": "unknown"}
        except TheWallConnectionError as err:
            LOGGER.debug("Cannot reach %s: %s", self._server, err)
            return {"base": "cannot_connect"}
        except Exception:
            LOGGER.exception("Unexpected error while pairing")
            return {"base": "unknown"}
        self._pairing = result["pairing"]
        length = result.get("length")
        self._length = length if isinstance(length, int) and length > 0 else 6
        self._attempts_left = ""
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the device ID and the server."""
        errors: dict[str, str] = {}
        if user_input is not None:
            uid = normalize_uid(user_input[CONF_DEVICE_ID])
            server = normalize_server(user_input.get(CONF_SERVER, DEFAULT_SERVER))
            if not uid:
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            elif server is None:
                errors[CONF_SERVER] = "invalid_url"
            else:
                await self.async_set_unique_id(uid, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._uid, self._server, self._name = uid, server, uid
                errors = await self._async_request_code()
                if not errors:
                    return await self.async_step_pair()
                if errors["base"] in ("unknown_device", "invalid_device_id"):
                    errors = {CONF_DEVICE_ID: errors["base"]}
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): TextSelector(),
                vol.Required(CONF_SERVER, default=DEFAULT_SERVER): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a THE WALL that announced itself on the network."""
        properties = discovery_info.properties
        uid = normalize_uid(str(properties.get("id") or ""))
        server = normalize_server(str(properties.get("srv") or DEFAULT_SERVER))
        if not uid or server is None:
            return self.async_abort(reason="invalid_discovery_info")
        await self.async_set_unique_id(uid)
        self._abort_if_unique_id_configured()
        self._uid, self._server = uid, server
        # The mDNS instance name, "Wall._thewall._tcp.local." becomes "Wall".
        self._name = (
            discovery_info.name.removesuffix(f".{ZEROCONF_TYPE}").strip() or uid
        )
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask before the panel shows a code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_request_code()
            if not errors:
                return await self.async_step_pair()
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders=self._placeholders(),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the code on the panel."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = normalize_code(user_input[CONF_CODE])
            if len(code) != self._length:
                errors["base"] = "invalid_code_length"
            else:
                result, errors = await self._async_confirm(code)
                if result is not None:
                    return self._async_finish(result)
                if errors.get("base") in ("pairing_expired", "too_many_attempts"):
                    return await self.async_step_restart(reason=errors["base"])
        return self.async_show_form(
            step_id="pair",
            data_schema=STEP_PAIR_SCHEMA,
            description_placeholders=self._placeholders(),
            errors=errors,
        )

    async def _async_confirm(
        self, code: str
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Send the code. Returns the response or form errors."""
        try:
            result = await self._client().confirm_pairing(
                self._pairing, code, PAIRING_NAME
            )
        except TheWallRateLimitError:
            return None, {"base": "rate_limited"}
        except TheWallApiError as err:
            if err.code == "invalid_code":
                if err.attempts_left is not None and err.attempts_left <= 0:
                    return None, {"base": "too_many_attempts"}
                self._attempts_left = (
                    str(err.attempts_left) if err.attempts_left is not None else "?"
                )
                return None, {"base": "invalid_code"}
            if err.code in _GONE_ERRORS:
                return None, {"base": "pairing_expired"}
            LOGGER.warning("Confirming the code failed: %s", err)
            return None, {"base": "unknown"}
        except TheWallConnectionError as err:
            LOGGER.debug("Cannot reach %s: %s", self._server, err)
            return None, {"base": "cannot_connect"}
        except Exception:
            LOGGER.exception("Unexpected error while confirming the code")
            return None, {"base": "unknown"}
        return result, {}

    async def async_step_restart(
        self, user_input: dict[str, Any] | None = None, reason: str | None = None
    ) -> ConfigFlowResult:
        """Offer a new code when the old one no longer works."""
        errors: dict[str, str] = {"base": reason} if reason else {}
        if user_input is not None:
            errors = await self._async_request_code()
            if not errors:
                return await self.async_step_pair()
        return self.async_show_form(
            step_id="restart",
            description_placeholders=self._placeholders(),
            errors=errors,
        )

    def _async_finish(self, result: dict[str, Any]) -> ConfigFlowResult:
        """Store the token, as a new entry or into the one being reauthenticated."""
        token: str = result["token"]
        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates={CONF_TOKEN: token},
            )
        device = result["state"].get("device") or {}
        title = device.get("name") or self._name or self._uid
        return self.async_create_entry(
            title=str(title),
            data={CONF_UID: self._uid, CONF_SERVER: self._server, CONF_TOKEN: token},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Pair again after the server rejected the token."""
        self._uid = entry_data[CONF_UID]
        self._server = entry_data[CONF_SERVER]
        self._name = self._get_reauth_entry().title
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pair again, the panel shows a new code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_request_code()
            if not errors:
                return await self.async_step_pair()
        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders=self._placeholders(),
            errors=errors,
        )
