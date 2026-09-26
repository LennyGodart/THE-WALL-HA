"""Config flow: user step, zeroconf, pairing with every error, reauth."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from unittest.mock import patch

from aiohttp import ClientConnectionError
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_USER,
    SOURCE_ZEROCONF,
    ConfigEntryState,
)
from homeassistant.const import CONF_CODE, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.thewall.const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_UID,
    DEFAULT_SERVER,
    DOMAIN,
)

from .conftest import setup_integration
from .fake_server import CODE, NEW_TOKEN, PAIRING, TOKEN, UID, FakeWall, error_body

OWN_SERVER = "https://wall.example.org"


def zeroconf_info(**properties: Any) -> ZeroconfServiceInfo:
    """What the device announces over mDNS."""
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.168.1.50"),
        ip_addresses=[ip_address("192.168.1.50")],
        port=80,
        hostname="wall-7f3a91.local.",
        type="_thewall._tcp.local.",
        name="Wall._thewall._tcp.local.",
        properties=properties or {"id": UID, "srv": DEFAULT_SERVER, "fw": "0.2.0"},
    )


async def start_user_flow(hass: HomeAssistant) -> dict[str, Any]:
    """Open the user step."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def configure(
    hass: HomeAssistant, result: dict[str, Any], user_input: dict[str, Any]
) -> dict[str, Any]:
    """Submit the current form."""
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def submit_device(
    hass: HomeAssistant,
    result: dict[str, Any],
    uid: str = UID,
    server: str = DEFAULT_SERVER,
) -> dict[str, Any]:
    """Submit the user step."""
    return await configure(hass, result, {CONF_DEVICE_ID: uid, CONF_SERVER: server})


async def at_pair_step(hass: HomeAssistant) -> dict[str, Any]:
    """Go through the user step to the code form."""
    result = await submit_device(hass, await start_user_flow(hass))
    assert result["step_id"] == "pair"
    return result


def assert_created(result: dict[str, Any], server: str = DEFAULT_SERVER) -> None:
    """The flow created the entry with uid, server and the new token."""
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wall"
    assert result["data"] == {CONF_UID: UID, CONF_SERVER: server, CONF_TOKEN: NEW_TOKEN}
    assert result["result"].unique_id == UID


async def test_user_flow(hass: HomeAssistant, wall: FakeWall) -> None:
    """Device ID, then the code from the panel, creates the entry."""
    result = await start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await submit_device(hass, result, uid=" Wall-7F3A91 ")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair"
    assert result["errors"] == {}
    assert result["description_placeholders"]["length"] == "6"
    assert result["description_placeholders"]["name"] == UID
    assert wall.payloads("/pair") == [{"device": UID}]

    # Lower case, spaces and dashes are fine.
    result = await configure(hass, result, {CONF_CODE: " k7q2-xm "})
    assert_created(result)
    assert wall.payloads("/pair/confirm") == [
        {"pairing": PAIRING, "code": CODE, "name": "Home Assistant"}
    ]
    await hass.async_block_till_done()
    assert result["result"].state is ConfigEntryState.LOADED


async def test_user_flow_own_server(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, state: dict[str, Any]
) -> None:
    """A server without scheme and with a trailing slash is cleaned up."""
    wall = FakeWall(aioclient_mock, state, server=OWN_SERVER)
    result = await submit_device(
        hass, await start_user_flow(hass), server=" wall.example.org/ "
    )
    assert result["step_id"] == "pair"
    assert result["description_placeholders"]["server"] == OWN_SERVER
    result = await configure(hass, result, {CONF_CODE: CODE})
    assert_created(result, server=OWN_SERVER)
    assert wall.count("/pair/confirm") == 1


@pytest.mark.parametrize(
    "server",
    ["ftp://wall.example.org", "https://", "https://wall.example.org/?a=1", "   "],
)
async def test_user_invalid_server(
    hass: HomeAssistant, wall: FakeWall, server: str
) -> None:
    """A server that is not an http(s) URL is refused before any request."""
    result = await submit_device(hass, await start_user_flow(hass), server=server)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_SERVER: "invalid_url"}
    assert wall.calls == []


async def test_user_empty_device_id(hass: HomeAssistant, wall: FakeWall) -> None:
    """An empty device ID is refused before any request."""
    result = await submit_device(hass, await start_user_flow(hass), uid="  ")
    assert result["errors"] == {CONF_DEVICE_ID: "invalid_device_id"}
    assert wall.calls == []


@pytest.mark.parametrize(
    ("status", "code", "field", "error"),
    [
        (404, "unknown_device", CONF_DEVICE_ID, "unknown_device"),
        (400, "bad_request", CONF_DEVICE_ID, "invalid_device_id"),
        (409, "device_offline", "base", "device_offline"),
        (429, "rate_limited", "base", "rate_limited"),
        (500, "server_error", "base", "unknown"),
    ],
)
async def test_user_pair_errors(
    hass: HomeAssistant,
    wall: FakeWall,
    status: int,
    code: str,
    field: str,
    error: str,
) -> None:
    """Errors from /pair keep the user step open, the next try works."""
    wall.fail("/pair", status, code)
    result = await submit_device(hass, await start_user_flow(hass))
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {field: error}

    result = await submit_device(hass, result)
    assert result["step_id"] == "pair"
    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


@pytest.mark.parametrize(
    "answer",
    [
        {"exc": ClientConnectionError("refused")},
        {"exc": TimeoutError()},
        {"status": 502, "text": "<html>Bad gateway</html>"},
        {"status": 200, "json": ["not", "an", "object"]},
        {"status": 200, "json": {"ok": True}},
    ],
    ids=["refused", "timeout", "html", "list", "no_pairing"],
)
async def test_user_cannot_connect(
    hass: HomeAssistant, wall: FakeWall, answer: dict[str, Any]
) -> None:
    """Anything that is not the API answering counts as cannot_connect."""
    wall.respond("/pair", **answer)
    result = await submit_device(hass, await start_user_flow(hass))
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_unexpected_error(hass: HomeAssistant, wall: FakeWall) -> None:
    """A bug shows as unknown instead of breaking the flow."""
    with patch(
        "custom_components.thewall.config_flow.TheWallClient.pair",
        side_effect=RuntimeError("bug"),
    ):
        result = await submit_device(hass, await start_user_flow(hass))
    assert result["errors"] == {"base": "unknown"}


async def test_user_already_configured(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """The same device cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await submit_device(hass, await start_user_flow(hass))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert wall.calls == []


async def test_user_flow_after_ignored_discovery(
    hass: HomeAssistant, wall: FakeWall
) -> None:
    """An ignored discovery does not block adding the device by hand."""
    MockConfigEntry(domain=DOMAIN, unique_id=UID, source=SOURCE_IGNORE).add_to_hass(
        hass
    )
    result = await at_pair_step(hass)
    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


async def test_pair_wrong_code(hass: HomeAssistant, wall: FakeWall) -> None:
    """A wrong code shows the attempts left, the right one still works."""
    result = await at_pair_step(hass)
    result = await configure(hass, result, {CONF_CODE: "AAAAAA"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair"
    assert result["errors"] == {"base": "invalid_code"}
    assert result["description_placeholders"]["attempts_left"] == "4"

    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


async def test_pair_code_length(hass: HomeAssistant, wall: FakeWall) -> None:
    """A code of the wrong length is refused without using up an attempt."""
    result = await at_pair_step(hass)
    result = await configure(hass, result, {CONF_CODE: "K7Q-2"})
    assert result["step_id"] == "pair"
    assert result["errors"] == {"base": "invalid_code_length"}
    assert wall.count("/pair/confirm") == 0


async def test_pair_too_many_attempts(hass: HomeAssistant, wall: FakeWall) -> None:
    """After the fifth wrong code the flow offers a new code."""
    wall.fail("/pair/confirm", 422, "invalid_code", attempts_left=0)
    result = await at_pair_step(hass)
    result = await configure(hass, result, {CONF_CODE: "AAAAAA"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "restart"
    assert result["errors"] == {"base": "too_many_attempts"}

    result = await configure(hass, result, {})
    assert result["step_id"] == "pair"
    assert wall.count("/pair") == 2
    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


async def test_pair_invalid_code_without_count(
    hass: HomeAssistant, wall: FakeWall
) -> None:
    """A server that leaves out attempts_left still gets a readable error."""
    wall.fail("/pair/confirm", 422, "invalid_code")
    result = await configure(hass, await at_pair_step(hass), {CONF_CODE: "AAAAAA"})
    assert result["errors"] == {"base": "invalid_code"}
    assert result["description_placeholders"]["attempts_left"] == "?"


@pytest.mark.parametrize(
    ("status", "code"), [(410, "pairing_expired"), (404, "unknown_pairing")]
)
async def test_pair_expired(
    hass: HomeAssistant, wall: FakeWall, status: int, code: str
) -> None:
    """An expired or unknown pairing offers a new code."""
    wall.fail("/pair/confirm", status, code)
    result = await configure(hass, await at_pair_step(hass), {CONF_CODE: CODE})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "restart"
    assert result["errors"] == {"base": "pairing_expired"}

    # The device went offline in the meantime: the step stays.
    wall.fail("/pair", 409, "device_offline")
    result = await configure(hass, result, {})
    assert result["step_id"] == "restart"
    assert result["errors"] == {"base": "device_offline"}

    result = await configure(hass, result, {})
    assert result["step_id"] == "pair"
    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        ({"status": 429, "json": error_body("rate_limited")}, "rate_limited"),
        ({"exc": ClientConnectionError("gone")}, "cannot_connect"),
        ({"status": 400, "json": error_body("bad_request")}, "unknown"),
        ({"status": 200, "json": {"ok": True, "token": "twha_x"}}, "cannot_connect"),
    ],
    ids=["rate_limited", "connection", "bad_request", "no_state"],
)
async def test_pair_confirm_errors(
    hass: HomeAssistant, wall: FakeWall, answer: dict[str, Any], error: str
) -> None:
    """Other errors keep the code form open."""
    wall.respond("/pair/confirm", **answer)
    result = await configure(hass, await at_pair_step(hass), {CONF_CODE: CODE})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair"
    assert result["errors"] == {"base": error}

    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


async def test_pair_confirm_unexpected_error(
    hass: HomeAssistant, wall: FakeWall
) -> None:
    """A bug while confirming shows as unknown."""
    result = await at_pair_step(hass)
    with patch(
        "custom_components.thewall.config_flow.TheWallClient.confirm_pairing",
        side_effect=RuntimeError("bug"),
    ):
        result = await configure(hass, result, {CONF_CODE: CODE})
    assert result["errors"] == {"base": "unknown"}


async def test_zeroconf_flow(hass: HomeAssistant, wall: FakeWall) -> None:
    """A discovered device asks first, then pairs like the user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"]["name"] == "Wall"
    assert result["description_placeholders"]["uid"] == UID
    assert result["description_placeholders"]["server"] == DEFAULT_SERVER
    progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert progress[0]["context"]["title_placeholders"] == {"name": "Wall"}
    assert wall.calls == []

    result = await configure(hass, result, {})
    assert result["step_id"] == "pair"
    assert wall.payloads("/pair") == [{"device": UID}]
    assert_created(await configure(hass, result, {CONF_CODE: CODE}))


async def test_zeroconf_own_server(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, state: dict[str, Any]
) -> None:
    """The srv TXT record points to another server."""
    FakeWall(aioclient_mock, state, server=OWN_SERVER)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=zeroconf_info(id=UID, srv=f"{OWN_SERVER}/"),
    )
    result = await configure(hass, result, {})
    assert_created(await configure(hass, result, {CONF_CODE: CODE}), server=OWN_SERVER)


async def test_zeroconf_without_server(hass: HomeAssistant, wall: FakeWall) -> None:
    """Without srv the default server is used."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info(id=UID)
    )
    assert result["description_placeholders"]["server"] == DEFAULT_SERVER


async def test_zeroconf_already_configured(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """A configured device is not offered again."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_already_in_progress(
    hass: HomeAssistant, wall: FakeWall
) -> None:
    """The same device announced twice gives one flow."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert first["type"] is FlowResultType.FORM
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"


@pytest.mark.parametrize(
    "properties",
    [
        {"srv": DEFAULT_SERVER, "fw": "0.2.0"},
        {"id": "  ", "srv": DEFAULT_SERVER},
        {"id": UID, "srv": "ftp://wall.example.org"},
    ],
    ids=["no_id", "empty_id", "bad_server"],
)
async def test_zeroconf_invalid(
    hass: HomeAssistant, wall: FakeWall, properties: dict[str, Any]
) -> None:
    """Announcements without a usable ID or server are dropped."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info(**properties)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery_info"


async def test_zeroconf_confirm_error(hass: HomeAssistant, wall: FakeWall) -> None:
    """If the panel cannot show a code, the confirm step says why."""
    wall.fail("/pair", 409, "device_offline")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    result = await configure(hass, result, {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert result["errors"] == {"base": "device_offline"}

    result = await configure(hass, result, {})
    assert result["step_id"] == "pair"


async def test_reauth(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """Reauth pairs the same device again and stores the new token."""
    await setup_integration(hass, config_entry)
    assert config_entry.data[CONF_TOKEN] == TOKEN

    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["name"] == "Wall"

    result = await configure(hass, result, {})
    assert result["step_id"] == "pair"
    assert wall.payloads("/pair") == [{"device": UID}]

    result = await configure(hass, result, {CONF_CODE: CODE})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert config_entry.data == {
        CONF_UID: UID,
        CONF_SERVER: DEFAULT_SERVER,
        CONF_TOKEN: NEW_TOKEN,
    }
    assert config_entry.state is ConfigEntryState.LOADED


async def test_reauth_error(
    hass: HomeAssistant, wall: FakeWall, config_entry: MockConfigEntry
) -> None:
    """A device deleted on the website cannot be paired again."""
    config_entry.add_to_hass(hass)
    wall.fail("/pair", 404, "unknown_device")
    result = await config_entry.start_reauth_flow(hass)
    result = await configure(hass, result, {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "unknown_device"}
