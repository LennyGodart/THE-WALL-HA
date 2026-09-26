"""The timer duration, stored in Home Assistant."""

from __future__ import annotations

from aiohttp import ClientConnectionError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from .conftest import setup_integration, tick
from .fake_server import FakeWall

ENTITY_ID = "number.wall_timer_duration"


async def set_minutes(hass: HomeAssistant, value: float) -> None:
    """Set the duration."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_VALUE: value},
        blocking=True,
    )


async def test_default(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Five minutes, 1 to 240."""
    state = hass.states.get(ENTITY_ID)
    assert float(state.state) == 5
    assert state.attributes[ATTR_MIN] == 1
    assert state.attributes[ATTR_MAX] == 240
    assert state.attributes[ATTR_STEP] == 1
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTime.MINUTES


async def test_set_value_stays_local(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Changing the duration sends nothing to the server."""
    await set_minutes(hass, 45)
    assert float(hass.states.get(ENTITY_ID).state) == 45
    assert wall.calls == [("GET", "/state", None)]


async def test_out_of_range(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Home Assistant keeps the value inside 1 to 240."""
    with pytest.raises(ServiceValidationError):
        await set_minutes(hass, 241)


async def test_restore(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """The last duration survives a restart and is used by the start button."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY_ID, "12"),
                {
                    "native_max_value": 240,
                    "native_min_value": 1,
                    "native_step": 1,
                    "native_unit_of_measurement": "min",
                    "native_value": 12,
                },
            )
        ],
    )
    await setup_integration(hass, config_entry)
    assert float(hass.states.get(ENTITY_ID).state) == 12

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.wall_start_timer"},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/timer", {"seconds": 720})


async def test_available_while_server_down(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The duration is local and stays available."""
    wall.respond("/state", exc=ClientConnectionError("down"))
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("light.wall").state == STATE_UNAVAILABLE
    assert float(hass.states.get(ENTITY_ID).state) == 5
