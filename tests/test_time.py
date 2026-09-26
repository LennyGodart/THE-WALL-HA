"""The alarm time."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.time import (
    ATTR_TIME,
    DOMAIN as TIME_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thewall.time import parse_hhmm

from .conftest import tick
from .fake_server import FakeWall

ENTITY_ID = "time.wall_alarm_time"


async def test_state(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """07:00 from the state."""
    assert hass.states.get(ENTITY_ID).state == "07:00:00"


async def test_set_value(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """HH:MM is sent, seconds are dropped."""
    await hass.services.async_call(
        TIME_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TIME: "06:30:45"},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/alarm", {"time": "06:30"})
    assert hass.states.get(ENTITY_ID).state == "06:30:00"


async def test_bad_time_from_server(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Something that is not HH:MM shows as unknown."""
    wall.state["alarm"]["time"] = "7 o'clock"
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("07:00", "07:00:00"),
        ("23:59", "23:59:00"),
        ("24:00", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_hhmm(value: object, expected: str | None) -> None:
    """Only valid times of day are accepted."""
    result = parse_hhmm(value)
    assert (result.isoformat() if result else None) == expected
