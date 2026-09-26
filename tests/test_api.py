"""The API client on its own: requests, error envelopes, helpers."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientConnectionError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.thewall.api import (
    TheWallApiError,
    TheWallAuthError,
    TheWallClient,
    TheWallConnectionError,
    TheWallRateLimitError,
    _parse_retry_after,
    normalize_code,
    normalize_server,
    normalize_uid,
)
from custom_components.thewall.const import DEFAULT_SERVER

from .fake_server import TOKEN, FakeWall

STATE_URL = f"{DEFAULT_SERVER}/api/ha/v1/state"


def client(hass: HomeAssistant, token: str | None = TOKEN) -> TheWallClient:
    """A client on the shared, mocked session."""
    return TheWallClient(async_get_clientsession(hass), f"{DEFAULT_SERVER}/", token)


async def test_headers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, wall: FakeWall
) -> None:
    """Bearer token on normal calls, none on pairing."""
    await client(hass).get_state()
    method, url, _data, headers = aioclient_mock.mock_calls[-1]
    assert method == "GET"
    assert str(url) == STATE_URL
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Accept"] == "application/json"

    await client(hass, token=None).pair("wall-7f3a91")
    headers = aioclient_mock.mock_calls[-1][3]
    assert "Authorization" not in headers


async def test_commands(hass: HomeAssistant, wall: FakeWall) -> None:
    """Every command sends the body of the contract."""
    api = client(hass)
    await api.set_panel(on=True, bright=10, mode="clock", rotation=["clock"])
    await api.set_note("A", "B")
    await api.hide_note()
    await api.start_timer(60, "Egg")
    await api.cancel_timer("a1b2c3d4")
    await api.cancel_timer()
    await api.set_alarm(on=True, time="06:00", days=[1, 2])
    await api.stop_ringing()
    await api.update_firmware()
    await api.unlink()
    assert wall.calls == [
        (
            "POST",
            "/panel",
            {"on": True, "bright": 10, "mode": "clock", "rotation": ["clock"]},
        ),
        ("POST", "/note", {"line1": "A", "line2": "B"}),
        ("POST", "/note/hide", {}),
        ("POST", "/timer", {"seconds": 60, "label": "Egg"}),
        ("POST", "/timer/cancel", {"id": "a1b2c3d4"}),
        ("POST", "/timer/cancel", {}),
        ("POST", "/alarm", {"on": True, "time": "06:00", "days": [1, 2]}),
        ("POST", "/ring/stop", {}),
        ("POST", "/firmware/update", {}),
        ("POST", "/unlink", {}),
    ]


@pytest.mark.parametrize(
    ("answer", "error", "code"),
    [
        (
            {"status": 401, "text": "<html>401</html>"},
            TheWallAuthError,
            "invalid_token",
        ),
        (
            {"status": 429, "text": "slow down", "headers": {"Retry-After": "12"}},
            TheWallRateLimitError,
            "rate_limited",
        ),
        (
            {
                "status": 422,
                "json": {"ok": False, "error": "plain", "code": "invalid_value"},
            },
            TheWallApiError,
            "invalid_value",
        ),
        ({"status": 200, "json": {"ok": False}}, TheWallApiError, "unknown"),
        (
            {"status": 200, "json": {"ok": True, "state": []}},
            TheWallConnectionError,
            None,
        ),
        ({"status": 200, "json": [1, 2]}, TheWallConnectionError, None),
        ({"status": 500, "text": ""}, TheWallConnectionError, None),
    ],
    ids=[
        "401_html",
        "429_html",
        "string_error",
        "ok_false",
        "bad_state",
        "list",
        "empty",
    ],
)
async def test_error_mapping(
    hass: HomeAssistant,
    wall: FakeWall,
    answer: dict[str, Any],
    error: type[Exception],
    code: str | None,
) -> None:
    """Each kind of answer maps to the right exception."""
    wall.respond("/state", **answer)
    with pytest.raises(error) as err:
        await client(hass).get_state()
    assert type(err.value) is error
    if code is not None:
        assert err.value.code == code
    if error is TheWallRateLimitError:
        assert err.value.retry_after == 12
    if code == "invalid_value":
        assert err.value.messages == {"en": "plain"}


async def test_error_envelope(hass: HomeAssistant, wall: FakeWall) -> None:
    """Status, code, both messages and attempts_left are kept."""
    wall.fail("/pair/confirm", 422, "invalid_code", attempts_left=3)
    with pytest.raises(TheWallApiError) as err:
        await client(hass).confirm_pairing("p", "k7q2-xm", "Home Assistant")
    assert err.value.status == 422
    assert err.value.code == "invalid_code"
    assert err.value.attempts_left == 3
    assert err.value.message("de") == "Deutscher Text zu invalid_code"
    assert err.value.message("de-CH") == "Deutscher Text zu invalid_code"
    assert err.value.message("fr") == "English text for invalid_code"
    assert "invalid_code (HTTP 422)" in str(err.value)
    # The code went out cleaned up.
    assert wall.last_call[2]["code"] == "K7Q2XM"


def test_message_fallback() -> None:
    """Without messages the code is the message."""
    assert TheWallApiError(500, "boom").message("de") == "boom"
    assert str(TheWallApiError(500, "boom")) == "boom (HTTP 500)"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30", 30.0),
        ("1.5", 1.5),
        ("0", None),
        ("-5", None),
        ("Wed, 21 Oct 2026 07:28:00 GMT", None),
        (None, None),
        ("", None),
    ],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    """Seconds only."""
    assert _parse_retry_after(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://thewall.godart.lu/", "https://thewall.godart.lu"),
        ("  thewall.godart.lu  ", "https://thewall.godart.lu"),
        ("http://192.168.1.2:8080", "http://192.168.1.2:8080"),
        ("https://example.org/wall/", "https://example.org/wall"),
        ("ftp://example.org", None),
        ("https://", None),
        ("https://example.org/?a=1", None),
        ("https://example.org/#top", None),
        ("http://[::1", None),
        ("", None),
    ],
)
def test_normalize_server(value: str, expected: str | None) -> None:
    """Only http and https URLs without query or fragment."""
    assert normalize_server(value) == expected


@pytest.mark.parametrize(
    ("exc", "text"),
    [
        (TimeoutError(), "Cannot reach the server: TimeoutError"),
        (ClientConnectionError("refused"), "Cannot reach the server: refused"),
    ],
)
async def test_connection_error_text(
    hass: HomeAssistant, wall: FakeWall, exc: Exception, text: str
) -> None:
    """The message names the problem, also when the exception has no text."""
    wall.respond("/state", exc=exc)
    with pytest.raises(TheWallConnectionError) as err:
        await client(hass).get_state()
    assert str(err.value) == text


async def test_confirm_without_token(hass: HomeAssistant, wall: FakeWall) -> None:
    """A confirm answer without a token is not usable."""
    wall.respond("/pair/confirm", json={"ok": True, "state": wall.snapshot()})
    with pytest.raises(TheWallConnectionError):
        await client(hass, token=None).confirm_pairing("p", "K7Q2XM", "Home Assistant")


def test_normalize_code_and_uid() -> None:
    """Codes lose spaces and dashes, IDs are lower case."""
    assert normalize_code(" k7q2-xm ") == "K7Q2XM"
    assert normalize_code("k7 q2 x\tm") == "K7Q2XM"
    assert normalize_uid("  WALL-7F3A91 ") == "wall-7f3a91"
