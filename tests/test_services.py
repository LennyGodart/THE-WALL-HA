"""The actions thewall.start_timer and thewall.cancel_timer."""

from __future__ import annotations

import copy
from typing import Any

from aiohttp import ClientConnectionError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
import voluptuous as vol

from custom_components.thewall.const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_UID,
    DOMAIN,
)

from .conftest import setup_integration
from .fake_server import TOKEN, FakeWall

OTHER_SERVER = "https://wall.example.org"
OTHER_UID = "wall-000001"


def device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """The device of an entry."""
    return dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0].id


async def start_timer(
    hass: HomeAssistant, data: dict[str, Any], *, response: bool = False
) -> Any:
    """Call thewall.start_timer."""
    return await hass.services.async_call(
        DOMAIN, "start_timer", data, blocking=True, return_response=response
    )


async def test_start_timer(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Start a timer on a device and get it back as response."""
    response = await start_timer(
        hass,
        {
            "device_id": device_id(hass, init_integration),
            "duration": {"hours": 0, "minutes": 5, "seconds": 0},
            "label": "Tea",
        },
        response=True,
    )
    assert wall.last_call == ("POST", "/timer", {"seconds": 300, "label": "Tea"})
    assert response == {
        "timer": {
            "id": "t0000001",
            "label": "Tea",
            "total": 300,
            "end": "2026-09-21T14:18:20+00:00",
        }
    }
    assert hass.states.get("sensor.wall_timer").attributes["count"] == 2


async def test_start_timer_without_response(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Without asking for a response, none is returned. No label, no label field."""
    result = await start_timer(hass, {"duration": "00:00:30"})
    assert result is None
    assert wall.last_call == ("POST", "/timer", {"seconds": 30})


async def test_target_as_list(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """A YAML target with a list of one device works, two do not."""
    device = device_id(hass, init_integration)
    await hass.services.async_call(
        DOMAIN,
        "start_timer",
        {"duration": 45},
        target={"device_id": [device]},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/timer", {"seconds": 45})
    with pytest.raises(vol.Invalid):
        await start_timer(hass, {"device_id": [device, device], "duration": 45})


async def test_start_timer_by_config_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The config entry works as target too."""
    await start_timer(
        hass, {"config_entry_id": init_integration.entry_id, "duration": 90}
    )
    assert wall.last_call == ("POST", "/timer", {"seconds": 90})


@pytest.mark.parametrize("duration", [0, "00:00:00", {"hours": 24, "seconds": 1}])
async def test_start_timer_invalid_duration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    duration: Any,
) -> None:
    """From 1 second to 24 hours."""
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"duration": duration})
    assert err.value.translation_key == "invalid_duration"
    assert wall.count("/timer") == 0


async def test_start_timer_label_too_long(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Labels hold 12 characters."""
    with pytest.raises(vol.Invalid):
        await start_timer(hass, {"duration": 60, "label": "Thirteen char"})
    assert wall.count("/timer") == 0


async def test_start_timer_both_targets(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Device and config entry together are ambiguous."""
    with pytest.raises(vol.Invalid):
        await start_timer(
            hass,
            {
                "device_id": device_id(hass, init_integration),
                "config_entry_id": init_integration.entry_id,
                "duration": 60,
            },
        )


async def test_too_many_timers(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The server allows five timers at once."""
    for _ in range(4):
        await start_timer(hass, {"duration": 60})
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"duration": 60})
    assert err.value.translation_key == "too_many_timers"


async def test_start_timer_connection_error(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Network errors reach the caller."""
    wall.respond("/timer", exc=ClientConnectionError("down"))
    with pytest.raises(HomeAssistantError) as err:
        await start_timer(hass, {"duration": 60})
    assert err.value.translation_key == "cannot_connect"


async def test_cancel_one_timer(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """With an ID only that timer goes."""
    await hass.services.async_call(
        DOMAIN, "cancel_timer", {"id": "a1b2c3d4"}, blocking=True
    )
    assert wall.last_call == ("POST", "/timer/cancel", {"id": "a1b2c3d4"})
    assert hass.states.get("binary_sensor.wall_timer_running").state == "off"


async def test_cancel_all_timers(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Without an ID all timers go."""
    await hass.services.async_call(
        DOMAIN,
        "cancel_timer",
        {"device_id": device_id(hass, init_integration)},
        blocking=True,
    )
    assert wall.last_call == ("POST", "/timer/cancel", {})


async def test_unknown_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A device ID that does not exist."""
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"device_id": "nope", "duration": 60})
    assert err.value.translation_key == "device_not_found"


async def test_device_of_other_integration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A device that is not a THE WALL."""
    other_entry = MockConfigEntry(domain="other")
    other_entry.add_to_hass(hass)
    other = device_registry.async_get_or_create(
        config_entry_id=other_entry.entry_id, identifiers={("other", "x")}
    )
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"device_id": other.id, "duration": 60})
    assert err.value.translation_key == "device_not_found"


async def test_unknown_config_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A config entry ID that does not exist."""
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"config_entry_id": "nope", "duration": 60})
    assert err.value.translation_key == "entry_not_found"


async def test_no_entries(hass: HomeAssistant) -> None:
    """The actions exist without any device, and say so."""
    assert await async_setup_component(hass, DOMAIN, {})
    assert hass.services.has_service(DOMAIN, "start_timer")
    assert hass.services.has_service(DOMAIN, "cancel_timer")
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"duration": 60})
    assert err.value.translation_key == "no_entries"


async def test_two_walls_need_a_target(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    state: dict[str, Any],
    wall: FakeWall,
) -> None:
    """With two devices the target is required, and picks the right one."""
    other_state = copy.deepcopy(state)
    other_state["device"].update(uid=OTHER_UID, name="Office")
    other_wall = FakeWall(aioclient_mock, other_state, server=OTHER_SERVER)
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office",
        unique_id=OTHER_UID,
        data={CONF_UID: OTHER_UID, CONF_SERVER: OTHER_SERVER, CONF_TOKEN: TOKEN},
    )
    await setup_integration(hass, other_entry)

    with pytest.raises(ServiceValidationError) as err:
        await start_timer(hass, {"duration": 60})
    assert err.value.translation_key == "target_required"

    await start_timer(hass, {"device_id": device_id(hass, other_entry), "duration": 60})
    assert other_wall.last_call == ("POST", "/timer", {"seconds": 60})
    assert wall.count("/timer") == 0


async def test_entry_not_loaded(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """A device that is not set up cannot take commands."""
    wall.respond("/state", exc=ClientConnectionError("down"))
    await setup_integration(hass, config_entry)
    with pytest.raises(ServiceValidationError) as err:
        await start_timer(
            hass, {"config_entry_id": config_entry.entry_id, "duration": 60}
        )
    assert err.value.translation_key == "entry_not_loaded"
    assert err.value.translation_placeholders == {"name": "Wall"}
