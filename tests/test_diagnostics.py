"""Diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.thewall.const import DEFAULT_SERVER

from .fake_server import TOKEN, UID


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    """The entry and the last state, without the token."""
    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)
    assert result["entry"]["title"] == "Wall"
    assert result["entry"]["data"] == {
        "uid": UID,
        "server": DEFAULT_SERVER,
        "token": "**REDACTED**",
    }
    assert result["last_update_success"] is True
    assert result["last_exception"] is None
    assert result["timer_minutes"] == 5
    assert result["state"]["device"]["uid"] == UID
    assert result["state"]["panel"]["mode"] == "flight"
    assert TOKEN not in json.dumps(result)
