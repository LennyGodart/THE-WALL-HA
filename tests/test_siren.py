"""The beep siren."""

from __future__ import annotations

from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.siren import (
    ATTR_DURATION,
    DOMAIN as SIREN_DOMAIN,
    SirenEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import tick
from .fake_server import FakeWall

SIREN = "siren.wall_beep"
RINGING = "binary_sensor.wall_ringing"


async def siren(hass: HomeAssistant, on: bool, **data: Any) -> None:
    """Turn the siren on or off."""
    await hass.services.async_call(
        SIREN_DOMAIN,
        SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: SIREN, **data},
        blocking=True,
    )


async def test_beep_on_and_off(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """On makes the wall beep until turned off; it counts as ringing."""
    state = hass.states.get(SIREN)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Wall Beep"
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
    )

    await siren(hass, True)
    assert wall.last_call == ("POST", "/beep", {"on": True})
    assert hass.states.get(SIREN).state == STATE_ON
    assert hass.states.get(RINGING).state == STATE_ON

    await siren(hass, False)
    assert wall.last_call == ("POST", "/beep", {"on": False})
    assert hass.states.get(SIREN).state == STATE_OFF
    assert hass.states.get(RINGING).state == STATE_OFF


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [(30, 30), (900, 900), (3600, 900), (0, 1)],
)
async def test_beep_duration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    duration: int,
    seconds: int,
) -> None:
    """The duration goes along in seconds, cut to the 15 minutes of any ringing."""
    await siren(hass, True, **{ATTR_DURATION: duration})
    assert wall.last_call == ("POST", "/beep", {"on": True, "seconds": seconds})


async def test_beep_ends_after_duration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The server ends the beep after the duration, the next poll shows it."""
    await siren(hass, True, **{ATTR_DURATION: 20})
    assert hass.states.get(SIREN).state == STATE_ON
    await tick(hass, frozen_clock, 21)
    assert hass.states.get(SIREN).state == STATE_OFF
    assert hass.states.get(RINGING).state == STATE_OFF


async def test_stop_ringing_ends_beep(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The stop ringing button ends the beep too."""
    await siren(hass, True)
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.wall_stop_ringing"},
        blocking=True,
    )
    assert hass.states.get(SIREN).state == STATE_OFF


async def test_siren_unavailable_on_older_server(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A server that cannot make the wall beep leaves the siren unavailable."""
    del wall.state["beep"]
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(SIREN).state == STATE_UNAVAILABLE
