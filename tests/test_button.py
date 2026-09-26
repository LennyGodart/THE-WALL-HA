"""The buttons."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .fake_server import FakeWall


async def press(hass: HomeAssistant, entity_id: str) -> None:
    """Press a button."""
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


@pytest.mark.parametrize(
    ("entity_id", "path", "payload"),
    [
        ("button.wall_hide_note", "/note/hide", {}),
        ("button.wall_stop_ringing", "/ring/stop", {}),
        ("button.wall_cancel_timers", "/timer/cancel", {}),
        ("button.wall_start_timer", "/timer", {"seconds": 300}),
    ],
)
async def test_buttons(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    entity_id: str,
    path: str,
    payload: dict[str, Any],
) -> None:
    """Each button sends its command."""
    await press(hass, entity_id)
    assert wall.last_call == ("POST", path, payload)


async def test_cancel_timers_clears_state(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The returned state has no timers left."""
    await press(hass, "button.wall_cancel_timers")
    assert hass.states.get("binary_sensor.wall_timer_running").state == "off"


async def test_start_timer_uses_duration(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The start button takes the minutes of the timer duration."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.wall_timer_duration", ATTR_VALUE: 12},
        blocking=True,
    )
    await press(hass, "button.wall_start_timer")
    assert wall.last_call == ("POST", "/timer", {"seconds": 720})
    assert hass.states.get("sensor.wall_timer").attributes["count"] == 2
