"""Online, ringing, timer running."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import tick
from .fake_server import FakeWall


async def test_states(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Online, not ringing, one timer running."""
    online = hass.states.get("binary_sensor.wall_online")
    assert online.state == STATE_ON
    assert online.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.CONNECTIVITY
    assert (
        entity_registry.async_get("binary_sensor.wall_online").entity_category
        is EntityCategory.DIAGNOSTIC
    )
    assert hass.states.get("binary_sensor.wall_ringing").state == STATE_OFF
    running = hass.states.get("binary_sensor.wall_timer_running")
    assert running.state == STATE_ON
    assert running.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.RUNNING


async def test_timer_rings(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """When the timer ends it rings and no timer runs any more."""
    await tick(hass, frozen_clock, 301)
    assert hass.states.get("binary_sensor.wall_ringing").state == STATE_ON
    assert hass.states.get("binary_sensor.wall_timer_running").state == STATE_OFF


async def test_alarm_rings(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A ringing alarm counts as ringing too."""
    wall.state["alarm"]["ringing"] = True
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("binary_sensor.wall_ringing").state == STATE_ON


async def test_offline(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The device can be offline while the server answers."""
    wall.state["device"]["online"] = False
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("binary_sensor.wall_online").state == STATE_OFF
    assert hass.states.get("light.wall").state == STATE_ON
