"""The two note lines."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.text import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_VALUE,
    DOMAIN as TEXT_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import tick
from .fake_server import FakeWall

LINE1 = "text.wall_note_line_1"
LINE2 = "text.wall_note_line_2"


async def set_value(hass: HomeAssistant, entity_id: str, value: str) -> None:
    """Change one line."""
    await hass.services.async_call(
        TEXT_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def test_state(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Both lines, at most 21 characters."""
    state = hass.states.get(LINE1)
    assert state.state == "DINNER AT 7"
    assert state.attributes[ATTR_MIN] == 0
    assert state.attributes[ATTR_MAX] == 21
    assert hass.states.get(LINE2).state == "BRING WINE"


async def test_set_line1_keeps_line2(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Line 1 is sent together with the current line 2."""
    await set_value(hass, LINE1, "LUNCH AT 12")
    assert wall.last_call == (
        "POST",
        "/note",
        {"line1": "LUNCH AT 12", "line2": "BRING WINE"},
    )
    assert hass.states.get(LINE1).state == "LUNCH AT 12"
    assert hass.states.get(LINE2).state == "BRING WINE"


async def test_set_line2_keeps_line1(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Line 2 is sent together with the current line 1."""
    await set_value(hass, LINE2, "")
    assert wall.last_call == ("POST", "/note", {"line1": "DINNER AT 7", "line2": ""})
    assert hass.states.get(LINE2).state == ""


async def test_both_lines_in_a_row(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The second change builds on the state the first one returned."""
    await set_value(hass, LINE1, "HELLO")
    await set_value(hass, LINE2, "WORLD")
    assert wall.payloads("/note") == [
        {"line1": "HELLO", "line2": "BRING WINE"},
        {"line1": "HELLO", "line2": "WORLD"},
    ]


async def test_too_long(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """More than fits on the panel is refused by Home Assistant."""
    with pytest.raises(ValueError, match="too long"):
        await set_value(hass, LINE1, "X" * 22)
    assert wall.count("/note") == 0


async def test_max_from_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The limit comes from note.max, with 21 as fallback."""
    wall.state["note"]["max"] = 16
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(LINE1).attributes[ATTR_MAX] == 16

    wall.state["note"]["max"] = None
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(LINE1).attributes[ATTR_MAX] == 21


async def test_missing_line(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A line that is not a string shows as unknown."""
    wall.state["note"]["line1"] = None
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(LINE1).state == STATE_UNKNOWN
