"""The mode select."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import tick
from .fake_server import FakeWall

ENTITY_ID = "select.wall_mode"


async def test_state(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """The options are the mode IDs the server offers."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == "flight"
    assert state.attributes[ATTR_OPTIONS] == [
        "flight",
        "clock",
        "weather",
        "transit",
        "spotify",
        "notes",
    ]


async def test_select_option(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Picking a mode sends it."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_OPTION: "clock"},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/panel", {"mode": "clock"})
    assert hass.states.get(ENTITY_ID).state == "clock"


async def test_unavailable_mode_is_refused(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """A mode the server does not offer never reaches it."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_OPTION: "pixel"},
            blocking=True,
        )
    assert wall.count("/panel") == 0


async def test_options_follow_server(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Modes that disappear or appear change the options."""
    modes = wall.state["panel"]["modes"]
    modes[:] = [mode for mode in modes if mode["id"] != "spotify"]
    modes.append(
        {"id": "pixel", "en": "Pixel editor", "de": "Pixel-Editor", "rotatable": True}
    )
    await tick(hass, frozen_clock, 15)
    options = hass.states.get(ENTITY_ID).attributes[ATTR_OPTIONS]
    assert "spotify" not in options
    assert "pixel" in options


async def test_current_mode_not_offered(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A mode outside the options shows as unknown."""
    wall.state["panel"]["mode"] = "screensaver"
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN
