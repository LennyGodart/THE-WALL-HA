"""The panel light."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_MODE,
    ATTR_SUPPORTED_COLOR_MODES,
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .fake_server import FakeWall

ENTITY_ID = "light.wall"


async def test_state(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """On, brightness 168, named after the device."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 168
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.BRIGHTNESS
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.BRIGHTNESS]
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Wall"


async def test_turn_off(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Turning off sends on: false and uses the returned state."""
    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )
    assert wall.last_call == ("POST", "/panel", {"on": False})
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    # No extra poll: the command response is the new state.
    assert wall.count("/state") == 1


@pytest.mark.parametrize(
    ("data", "payload", "brightness"),
    [
        ({}, {"on": True}, 168),
        ({ATTR_BRIGHTNESS: 50}, {"on": True, "bright": 50}, 50),
        ({ATTR_BRIGHTNESS: 1}, {"on": True, "bright": 1}, 1),
        ({ATTR_BRIGHTNESS_PCT: 100}, {"on": True, "bright": 255}, 255),
    ],
)
async def test_turn_on(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    data: dict[str, Any],
    payload: dict[str, Any],
    brightness: int,
) -> None:
    """Brightness maps 1:1 to the server value."""
    wall.state["panel"]["on"] = False
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/panel", payload)
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == brightness


async def test_brightness_zero_turns_off(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Home Assistant turns brightness 0 into turn_off."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_BRIGHTNESS: 0},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/panel", {"on": False})
