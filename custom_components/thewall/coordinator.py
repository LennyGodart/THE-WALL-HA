"""Coordinator for THE WALL: one per device, polling /state every 15 seconds."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    TheWallApiError,
    TheWallAuthError,
    TheWallClient,
    TheWallConnectionError,
    TheWallRateLimitError,
)
from .const import (
    CONF_UID,
    DOMAIN,
    EVENT_REFRESH_DELAY,
    LOGGER,
    TIMER_DEFAULT_MINUTES,
    UPDATE_INTERVAL,
)

type TheWallConfigEntry = ConfigEntry[TheWallCoordinator]

# Refusals caused by what was asked for, not by the server or the network.
_VALIDATION_CODES = {"invalid_value", "too_many_timers", "no_update"}
# Codes with their own message. The rest show the server message.
_OWN_MESSAGE_CODES = {"too_many_timers", "no_update"}


def configuration_url(device: dict[str, Any]) -> str | None:
    """Return the device page on the website, if the server sent a usable URL."""
    url = device.get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url
    return None


class TheWallCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hold the STATE of one device."""

    config_entry: TheWallConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: TheWallConfigEntry, client: TheWallClient
    ) -> None:
        """Set up polling for one config entry."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.uid: str = entry.data[CONF_UID]
        # Minutes for the "Start timer" button. The number entity owns and
        # restores the value, the button reads it here.
        self.timer_minutes: float = TIMER_DEFAULT_MINUTES
        self._unsub_event_refresh: CALLBACK_TYPE | None = None
        self._event_refresh_job = HassJob(
            self._async_event_refresh,
            "thewall event refresh",
            cancel_on_shutdown=True,
        )

    @property
    def language(self) -> str:
        """Language for messages the server sends in English and German."""
        return self.hass.config.language or "en"

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the state."""
        try:
            return await self.client.get_state()
        except TheWallAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_token"
            ) from err
        except TheWallRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=err.retry_after,
            ) from err
        except TheWallApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"message": err.message(self.language)},
            ) from err
        except TheWallConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_command(
        self, command: Callable[[], Awaitable[dict[str, Any]]]
    ) -> dict[str, Any]:
        """Run a command and use the state it returns right away.

        Returns the whole response, for the parts next to the state such as
        the new timer.
        """
        try:
            response = await command()
        except TheWallAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_token"
            ) from err
        except TheWallRateLimitError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="rate_limited"
            ) from err
        except TheWallApiError as err:
            error_cls = (
                ServiceValidationError
                if err.code in _VALIDATION_CODES
                else HomeAssistantError
            )
            if err.code in _OWN_MESSAGE_CODES:
                raise error_cls(
                    translation_domain=DOMAIN, translation_key=err.code
                ) from err
            raise error_cls(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"message": err.message(self.language)},
            ) from err
        except TheWallConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_set_updated_data(response["state"])
        return response

    @callback
    def _async_refresh_finished(self) -> None:
        """Run after every poll, before entities are told."""
        if self.last_update_success:
            self._async_after_update()

    @callback
    def async_set_updated_data(self, data: dict[str, Any]) -> None:
        """Take a state from a command response."""
        super().async_set_updated_data(data)
        self._async_after_update()

    @callback
    def _async_after_update(self) -> None:
        """Keep the device registry current and plan the next event refresh."""
        self._async_update_device_registry()
        self._async_schedule_event_refresh()

    @callback
    def _async_update_device_registry(self) -> None:
        """Follow firmware, name and model changes made outside Home Assistant."""
        registry = dr.async_get(self.hass)
        # Looked up through the config entry: async_get_device is deprecated
        # since 2026.9, and its replacement does not exist in 2026.3.
        entry = next(
            (
                device
                for device in dr.async_entries_for_config_entry(
                    registry, self.config_entry.entry_id
                )
                if (DOMAIN, self.uid) in device.identifiers
            ),
            None,
        )
        if entry is None:
            return
        device = self.data.get("device") or {}
        changes: dict[str, Any] = {}
        if (fw := device.get("fw")) and fw != entry.sw_version:
            changes["sw_version"] = fw
        if (name := device.get("name")) and name != entry.name:
            changes["name"] = name
        if (model := device.get("model")) and model != entry.model:
            changes["model"] = model
        if (url := configuration_url(device)) and url != entry.configuration_url:
            changes["configuration_url"] = url
        if changes:
            registry.async_update_device(entry.id, **changes)

    @callback
    def _async_schedule_event_refresh(self) -> None:
        """Refresh once a second after the next timer end or alarm time.

        Polling alone would report a ringing timer up to 15 seconds late. The
        delay is counted in server time, so a skewed clock here does not matter.
        """
        if self._unsub_event_refresh is not None:
            self._unsub_event_refresh()
            self._unsub_event_refresh = None
        data = self.data or {}
        now = data.get("time")
        if not isinstance(now, int | float):
            now = time.time()
        moments: list[Any] = [
            timer.get("end")
            for timer in data.get("timers") or []
            if isinstance(timer, dict) and not timer.get("ringing")
        ]
        alarm = data.get("alarm") or {}
        if alarm.get("on") and not alarm.get("ringing"):
            moments.append(alarm.get("next"))
        upcoming = [m for m in moments if isinstance(m, int | float) and m > now]
        if not upcoming:
            return
        self._unsub_event_refresh = async_call_later(
            self.hass,
            min(upcoming) - now + EVENT_REFRESH_DELAY,
            self._event_refresh_job,
        )

    async def _async_event_refresh(self, _now: datetime) -> None:
        """Poll right after a timer or the alarm went off."""
        self._unsub_event_refresh = None
        await self.async_refresh()

    async def async_shutdown(self) -> None:
        """Cancel the event refresh as well."""
        if self._unsub_event_refresh is not None:
            self._unsub_event_refresh()
            self._unsub_event_refresh = None
        await super().async_shutdown()
