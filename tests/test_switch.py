"""The alarm switch and the rotation switches."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import tick
from .fake_server import FakeWall

ROTATION = {
    "flight": "switch.wall_rotation_flight_radar",
    "clock": "switch.wall_rotation_clock",
    "weather": "switch.wall_rotation_weather",
    "transit": "switch.wall_rotation_departures",
    "spotify": "switch.wall_rotation_spotify",
}


async def switch(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    """Turn a switch on or off."""
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )


async def test_alarm_switch(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The alarm is set and cleared with on."""
    assert hass.states.get("switch.wall_alarm").state == STATE_OFF

    await switch(hass, "switch.wall_alarm", True)
    assert wall.last_call == ("POST", "/alarm", {"on": True})
    assert hass.states.get("switch.wall_alarm").state == STATE_ON

    await switch(hass, "switch.wall_alarm", False)
    assert wall.last_call == ("POST", "/alarm", {"on": False})
    assert hass.states.get("switch.wall_alarm").state == STATE_OFF


async def test_rotation_switches_disabled_by_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """One configuration switch per rotatable mode, disabled at first."""
    for entity_id in ROTATION.values():
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert entry.entity_category is EntityCategory.CONFIG
    # Notes cannot be in the rotation.
    assert entity_registry.async_get("switch.wall_rotation_notes") is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_rotation_toggle(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Toggling sends the whole list with the mode added or removed."""
    assert hass.states.get(ROTATION["flight"]).state == STATE_ON
    assert hass.states.get(ROTATION["clock"]).state == STATE_ON
    assert hass.states.get(ROTATION["weather"]).state == STATE_OFF
    assert hass.states.get(ROTATION["flight"]).attributes[ATTR_FRIENDLY_NAME] == (
        "Wall Rotation: Flight radar"
    )

    await switch(hass, ROTATION["weather"], True)
    assert wall.last_call == (
        "POST",
        "/panel",
        {"rotation": ["flight", "clock", "weather"]},
    )
    assert hass.states.get(ROTATION["weather"]).state == STATE_ON

    await switch(hass, ROTATION["flight"], False)
    assert wall.last_call == ("POST", "/panel", {"rotation": ["clock", "weather"]})
    assert hass.states.get(ROTATION["flight"]).state == STATE_OFF

    # Turning on what is already on keeps a single entry.
    await switch(hass, ROTATION["clock"], True)
    assert wall.last_call == ("POST", "/panel", {"rotation": ["weather", "clock"]})


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_rotation_mode_added_later(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
    entity_registry: er.EntityRegistry,
) -> None:
    """A mode that appears later gets its switch without a reload.

    Unknown to this integration, it is named the way the server names it.
    """
    wall.state["panel"]["modes"].append(
        {"id": "pixel", "en": "Pixel editor", "de": "Pixel-Editor", "rotatable": True}
    )
    await tick(hass, frozen_clock, 15)
    entity_id = "switch.wall_rotation_pixel_editor"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Wall Rotation: Pixel editor"

    await switch(hass, entity_id, True)
    assert wall.last_call == (
        "POST",
        "/panel",
        {"rotation": ["flight", "clock", "pixel"]},
    )

    # A second poll does not add it twice.
    await tick(hass, frozen_clock, 15)
    assert (
        len(
            [
                entry
                for entry in er.async_entries_for_config_entry(
                    entity_registry, init_integration.entry_id
                )
                if entry.unique_id.endswith("rotation_pixel")
            ]
        )
        == 1
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_rotation_mode_removed(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A mode the server no longer offers makes its switch unavailable."""
    modes = wall.state["panel"]["modes"]
    modes[:] = [mode for mode in modes if mode["id"] != "spotify"]
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(ROTATION["spotify"]).state == STATE_UNAVAILABLE
    assert hass.states.get(ROTATION["clock"]).state == STATE_ON
