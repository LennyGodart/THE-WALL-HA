"""Actions: thewall.start_timer and thewall.cancel_timer."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN, TIMER_LABEL_MAX, TIMER_MAX_SECONDS
from .coordinator import TheWallConfigEntry, TheWallCoordinator

SERVICE_START_TIMER = "start_timer"
SERVICE_CANCEL_TIMER = "cancel_timer"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DURATION = "duration"
ATTR_LABEL = "label"
ATTR_TIMER_ID = "id"


def _one_id(value: Any) -> str:
    """Accept an ID, or a list with one ID as a YAML target gives it."""
    if isinstance(value, list):
        if len(value) != 1:
            raise vol.Invalid("pick exactly one THE WALL")
        value = value[0]
    return cv.string(value)


# The wall is picked by device, or by config entry. With a single wall
# neither is needed.
_TARGET = {
    vol.Exclusive(ATTR_DEVICE_ID, "target"): _one_id,
    vol.Exclusive(ATTR_CONFIG_ENTRY_ID, "target"): _one_id,
}

START_TIMER_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required(ATTR_DURATION): cv.time_period,
        vol.Optional(ATTR_LABEL): vol.All(cv.string, vol.Length(max=TIMER_LABEL_MAX)),
    }
)

CANCEL_TIMER_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Optional(ATTR_TIMER_ID): cv.string,
    }
)


def _not_found(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def _entry_for_device(hass: HomeAssistant, device_id: str) -> TheWallConfigEntry:
    """Return the config entry behind a device of this integration.

    Found by the uid in the device identifiers. That works the same before and
    after the device registry changes of Home Assistant 2026.9.
    """
    entry: TheWallConfigEntry | None = None
    if (device := dr.async_get(hass).async_get(device_id)) is not None:
        for domain, uid in device.identifiers:
            if domain == DOMAIN:
                entry = hass.config_entries.async_entry_for_domain_unique_id(
                    DOMAIN, uid
                )
                break
    if entry is None:
        raise _not_found("device_not_found", device_id=device_id)
    return entry


def _coordinator(call: ServiceCall) -> TheWallCoordinator:
    """Find the wall an action is meant for."""
    hass = call.hass
    entry: TheWallConfigEntry | None
    if device_id := call.data.get(ATTR_DEVICE_ID):
        entry = _entry_for_device(hass, device_id)
    elif entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise _not_found("entry_not_found", entry_id=entry_id)
    else:
        entries = hass.config_entries.async_entries(
            DOMAIN, include_ignore=False, include_disabled=False
        )
        if not entries:
            raise _not_found("no_entries")
        if len(entries) > 1:
            raise _not_found("target_required")
        entry = entries[0]
    if entry.state is not ConfigEntryState.LOADED:
        raise _not_found("entry_not_loaded", name=entry.title)
    return entry.runtime_data


def _timer_response(timer: dict[str, Any]) -> dict[str, Any]:
    """Return the timer for the action response, with the end as ISO 8601."""
    end = timer.get("end")
    return {
        "id": timer.get("id"),
        "label": timer.get("label") or None,
        "total": timer.get("total"),
        "end": (
            dt_util.utc_from_timestamp(end).isoformat()
            if isinstance(end, int | float) and not isinstance(end, bool)
            else None
        ),
    }


async def _async_start_timer(call: ServiceCall) -> ServiceResponse:
    """Start a timer on the panel."""
    duration: timedelta = call.data[ATTR_DURATION]
    seconds = round(duration.total_seconds())
    if not 1 <= seconds <= TIMER_MAX_SECONDS:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_duration",
            translation_placeholders={"max": str(TIMER_MAX_SECONDS)},
        )
    coordinator = _coordinator(call)
    label: str | None = call.data.get(ATTR_LABEL)
    response = await coordinator.async_command(
        lambda: coordinator.client.start_timer(seconds, label)
    )
    if not call.return_response:
        return None
    timer = response.get("timer")
    return {"timer": _timer_response(timer if isinstance(timer, dict) else {})}


async def _async_cancel_timer(call: ServiceCall) -> None:
    """Cancel one timer, or all of them."""
    coordinator = _coordinator(call)
    timer_id: str | None = call.data.get(ATTR_TIMER_ID)
    await coordinator.async_command(lambda: coordinator.client.cancel_timer(timer_id))


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions once, independent of config entries."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_TIMER,
        _async_start_timer,
        schema=START_TIMER_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_TIMER,
        _async_cancel_timer,
        schema=CANCEL_TIMER_SCHEMA,
    )
