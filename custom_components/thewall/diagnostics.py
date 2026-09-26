"""Diagnostics for THE WALL. The token never leaves Home Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import TheWallConfigEntry

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TheWallConfigEntry
) -> dict[str, Any]:
    """Return the entry, the last state and whether polling works."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "last_update_success": coordinator.last_update_success,
        "last_exception": (
            repr(coordinator.last_exception) if coordinator.last_exception else None
        ),
        "timer_minutes": coordinator.timer_minutes,
        "state": coordinator.data,
    }
