"""Setup, unload, removal, polling, the extra refresh and command errors."""

from __future__ import annotations

from aiohttp import ClientConnectionError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thewall import async_remove_entry
from custom_components.thewall.const import DOMAIN

from .conftest import NOW_TS, setup_integration, tick
from .fake_server import UID, FakeWall


async def turn_off_panel(hass: HomeAssistant) -> None:
    """Send any command, here: switch the panel off."""
    await hass.services.async_call(
        LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: "light.wall"}, blocking=True
    )


def reauth_flows(hass: HomeAssistant) -> list[dict]:
    """Reauth flows in progress for THE WALL."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == SOURCE_REAUTH
    ]


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The entry loads, creates entities and unloads again."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get("light.wall").state == STATE_ON
    assert wall.count("/state") == 1

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    "answer",
    [
        {"exc": ClientConnectionError("down")},
        {"status": 503, "text": "maintenance"},
        {"status": 500, "json": {"ok": False, "code": "boom"}},
        {"status": 200, "json": {"ok": True, "state": {"device": {}}}},
    ],
    ids=["connection", "html", "api_error", "broken_state"],
)
async def test_setup_retry(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry, answer: dict
) -> None:
    """Without a state, setup is retried later."""
    wall.respond("/state", **answer)
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retry_when_rate_limited(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """429 during setup is retried as well."""
    wall.fail("/state", 429, "rate_limited", headers={"Retry-After": "30"})
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_auth_failed_starts_reauth(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """A revoked token stops setup and asks to pair again."""
    wall.token = None
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = reauth_flows(hass)
    assert len(flows) == 1
    assert flows[0]["context"]["entry_id"] == config_entry.entry_id


async def test_polling(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The state is fetched every 15 seconds."""
    wall.state["panel"]["on"] = False
    await tick(hass, frozen_clock, 14)
    assert wall.count("/state") == 1
    await tick(hass, frozen_clock, 1)
    assert wall.count("/state") == 2
    assert hass.states.get("light.wall").state == STATE_OFF


async def test_polling_failure_and_recovery(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Entities are unavailable while the server is unreachable."""
    wall.respond("/state", exc=ClientConnectionError("down"))
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("light.wall").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.wall_callsign").state == STATE_UNAVAILABLE

    await tick(hass, frozen_clock, 15)
    assert hass.states.get("light.wall").state == STATE_ON


async def test_polling_auth_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A token revoked while running makes entities unavailable and starts reauth."""
    wall.token = None
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("light.wall").state == STATE_UNAVAILABLE
    assert len(reauth_flows(hass)) == 1


async def test_rate_limit_waits_for_retry_after(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """After 429 the next poll waits as long as Retry-After says."""
    wall.fail("/state", 429, "rate_limited", headers={"Retry-After": "60"})
    await tick(hass, frozen_clock, 15)
    assert wall.count("/state") == 2
    assert hass.states.get("light.wall").state == STATE_UNAVAILABLE

    await tick(hass, frozen_clock, 45)
    assert wall.count("/state") == 2
    await tick(hass, frozen_clock, 16)
    assert wall.count("/state") == 3
    assert hass.states.get("light.wall").state == STATE_ON


async def test_remove_entry_unlinks(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Removing the entry revokes the token on the server."""
    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert wall.last_call == ("POST", "/unlink", {})
    assert wall.token is None


async def test_remove_entry_ignores_errors(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The entry goes away even if the server cannot be reached."""
    wall.respond("/unlink", exc=ClientConnectionError("down"))
    await hass.config_entries.async_remove(init_integration.entry_id)
    await hass.async_block_till_done()
    assert wall.count("/unlink") == 1
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_remove_ignored_entry(hass: HomeAssistant, wall: FakeWall) -> None:
    """An ignored discovery has no token, nothing is sent."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UID, source=SOURCE_IGNORE)
    entry.add_to_hass(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert wall.calls == []


async def test_remove_entry_without_token(hass: HomeAssistant, wall: FakeWall) -> None:
    """The removal hook does nothing for an entry without a token."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=UID, data={})
    await async_remove_entry(hass, entry)
    assert wall.calls == []


async def test_sparse_state(
    hass: HomeAssistant,
    wall: FakeWall,
    config_entry: MockConfigEntry,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A state without time and timers still works, with nothing to schedule."""
    state = wall.snapshot()
    del state["time"]
    state["timers"] = None
    wall.respond("/state", json={"ok": True, "state": state}, times=2)
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.wall_timer_running").state == STATE_OFF
    assert hass.states.get("sensor.wall_timer").state == "unknown"
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("event.wall_timer").state == "unknown"
    assert wall.count("/state") == 2


async def test_device_info(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """One device with the data of the state."""
    devices = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {(DOMAIN, UID)}
    assert device.name == "Wall"
    assert device.manufacturer == "THE WALL"
    assert device.model == "THE WALL 128x64"
    assert device.sw_version == "0.2.0"
    assert device.serial_number == UID
    assert device.configuration_url == "https://thewall.godart.lu/device/5"


async def test_device_registry_follows_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    device_registry: dr.DeviceRegistry,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Firmware, name, model and URL changes reach the device registry."""
    wall.state["device"].update(
        fw="0.2.1",
        name="Kitchen wall",
        model="THE WALL 128x64 rev B",
        url="https://thewall.godart.lu/device/6",
    )
    await tick(hass, frozen_clock, 15)
    device = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )[0]
    assert device.sw_version == "0.2.1"
    assert device.name == "Kitchen wall"
    assert device.model == "THE WALL 128x64 rev B"
    assert device.configuration_url == "https://thewall.godart.lu/device/6"


async def test_device_without_url(
    hass: HomeAssistant,
    wall: FakeWall,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A missing or odd URL leaves the configuration URL empty."""
    wall.state["device"]["url"] = "/device/5"
    await setup_integration(hass, config_entry)
    device = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)[
        0
    ]
    assert device.configuration_url is None


async def test_refresh_right_after_timer_end(
    hass: HomeAssistant,
    wall: FakeWall,
    config_entry: MockConfigEntry,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A second after a timer ends the state is fetched, not up to 15 s later."""
    wall.state["timers"][0]["end"] = NOW_TS + 20
    await setup_integration(hass, config_entry)
    await tick(hass, frozen_clock, 15)
    assert wall.count("/state") == 2
    assert hass.states.get("binary_sensor.wall_ringing").state == STATE_OFF

    await tick(hass, frozen_clock, 6)
    assert wall.count("/state") == 3
    assert hass.states.get("binary_sensor.wall_ringing").state == STATE_ON


async def test_refresh_right_after_alarm(
    hass: HomeAssistant,
    wall: FakeWall,
    config_entry: MockConfigEntry,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The same for the alarm time."""
    wall.state["timers"] = []
    wall.state["alarm"].update(on=True, next=NOW_TS + 40)
    await setup_integration(hass, config_entry)
    await tick(hass, frozen_clock, 15)
    await tick(hass, frozen_clock, 15)
    assert wall.count("/state") == 3
    # The regular poll would come at 45 seconds.
    await tick(hass, frozen_clock, 11)
    assert wall.count("/state") == 4


async def test_no_extra_refresh_without_timer_or_alarm(
    hass: HomeAssistant,
    wall: FakeWall,
    config_entry: MockConfigEntry,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Without anything due, only the regular polls happen."""
    wall.state["timers"] = []
    await setup_integration(hass, config_entry)
    await tick(hass, frozen_clock, 14)
    assert wall.count("/state") == 1


@pytest.mark.parametrize(
    ("status", "code", "error_type", "key"),
    [
        (422, "invalid_value", ServiceValidationError, "api_error"),
        (500, "bad_request", HomeAssistantError, "api_error"),
        (429, "rate_limited", HomeAssistantError, "rate_limited"),
    ],
)
async def test_command_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    status: int,
    code: str,
    error_type: type[HomeAssistantError],
    key: str,
) -> None:
    """Server errors on commands become translated errors."""
    wall.fail("/panel", status, code)
    with pytest.raises(error_type) as err:
        await turn_off_panel(hass)
    assert type(err.value) is error_type
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == key
    if key == "api_error":
        assert err.value.translation_placeholders == {
            "message": f"English text for {code}"
        }
    # Nothing changed.
    assert hass.states.get("light.wall").state == STATE_ON


async def test_command_error_in_german(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """The server message follows the language of Home Assistant."""
    hass.config.language = "de"
    wall.fail("/panel", 422, "invalid_value")
    with pytest.raises(ServiceValidationError) as err:
        await turn_off_panel(hass)
    assert err.value.translation_placeholders == {
        "message": "Deutscher Text zu invalid_value"
    }


@pytest.mark.parametrize(
    "answer",
    [
        {"exc": ClientConnectionError("down")},
        {"status": 200, "json": {"ok": True}},
    ],
    ids=["connection", "no_state"],
)
async def test_command_cannot_connect(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall, answer: dict
) -> None:
    """Network errors and answers without a state."""
    wall.respond("/panel", **answer)
    with pytest.raises(HomeAssistantError) as err:
        await turn_off_panel(hass)
    assert err.value.translation_key == "cannot_connect"


async def test_command_auth_error_starts_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """A command with a revoked token asks to pair again."""
    wall.token = None
    with pytest.raises(HomeAssistantError) as err:
        await turn_off_panel(hass)
    assert err.value.translation_key == "invalid_token"
    await hass.async_block_till_done()
    assert len(reauth_flows(hass)) == 1
