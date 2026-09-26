"""The firmware update."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.update import (
    ATTR_IN_PROGRESS,
    ATTR_INSTALLED_VERSION,
    ATTR_LATEST_VERSION,
    DOMAIN as UPDATE_DOMAIN,
    SERVICE_INSTALL,
    UpdateEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thewall.const import DOMAIN

from .conftest import tick
from .fake_server import FakeWall

ENTITY_ID = "update.wall_firmware"


async def install(hass: HomeAssistant) -> None:
    """Press install."""
    await hass.services.async_call(
        UPDATE_DOMAIN, SERVICE_INSTALL, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )


async def test_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """0.2.0 installed, 0.2.1 available."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INSTALLED_VERSION] == "0.2.0"
    assert state.attributes[ATTR_LATEST_VERSION] == "0.2.1"
    assert state.attributes[ATTR_IN_PROGRESS] is False
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    assert entity_registry.async_get(ENTITY_ID).entity_category is EntityCategory.CONFIG


async def test_install(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Install asks the server, the request shows as in progress until done."""
    await install(hass)
    assert wall.last_call == ("POST", "/firmware/update", {})
    assert hass.states.get(ENTITY_ID).attributes[ATTR_IN_PROGRESS] is True

    # A second install while the device has not picked it up is refused.
    with pytest.raises(HomeAssistantError):
        await install(hass)
    assert wall.count("/firmware/update") == 1

    # The device installed it and reports the new version.
    wall.state["device"].update(fw="0.2.1", fw_latest=None, fw_requested=False)
    await tick(hass, frozen_clock, 15)
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_IN_PROGRESS] is False
    assert state.attributes[ATTR_LATEST_VERSION] == "0.2.1"


async def test_install_when_server_has_nothing_newer(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """409 no_update, for example right after another client started it."""
    wall.fail("/firmware/update", 409, "no_update")
    with pytest.raises(ServiceValidationError) as err:
        await install(hass)
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "no_update"


async def test_up_to_date(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Without fw_latest the installed version is the latest."""
    wall.state["device"]["fw_latest"] = None
    await tick(hass, frozen_clock, 15)
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_LATEST_VERSION] == "0.2.0"


async def test_unknown_firmware(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A device that never reported its version."""
    wall.state["device"].update(fw=None, fw_latest=None)
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN
