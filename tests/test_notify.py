"""Notes through notify.send_message."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.notify import (
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thewall.notify import wrap_note

from .conftest import NOW, tick
from .fake_server import FakeWall

ENTITY_ID = "notify.wall_note"


@pytest.mark.parametrize(
    ("message", "lines"),
    [
        ("Dinner is ready", ("Dinner is ready", "")),
        (
            "The washing machine has finished its program",
            ("The washing machine", "has finished its"),
        ),
        (
            "Supercalifragilisticexpialidocious",
            ("Supercalifragilistice", "xpialidocious"),
        ),
        ("Door open", ("Door open", "")),
        ("  spaced   out\nover lines ", ("spaced out over lines", "")),
        ("x" * 50, ("x" * 21, "x" * 21)),
        ("Exactly twenty one ch next line", ("Exactly twenty one ch", "next line")),
        (
            "Hi Supercalifragilisticexpialidocious",
            ("Hi", "Supercalifragilistice"),
        ),
        ("", ("", "")),
    ],
)
def test_wrap_note(message: str, lines: tuple[str, str]) -> None:
    """Break at word boundaries, cut words longer than a line."""
    assert wrap_note(message, 21) == lines


async def test_send_message(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """Without a title the message is wrapped into two lines."""
    assert hass.states.get(ENTITY_ID).state == STATE_UNKNOWN
    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_MESSAGE: "The washing machine has finished its program",
        },
        blocking=True,
    )
    assert wall.last_call == (
        "POST",
        "/note",
        {"line1": "The washing machine", "line2": "has finished its"},
    )
    assert hass.states.get("text.wall_note_line_1").state == "The washing machine"
    assert hass.states.get(ENTITY_ID).state == NOW.isoformat()


async def test_send_message_with_title(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """With a title, the title is line 1 and the message line 2."""
    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_TITLE: "Laundry",
            ATTR_MESSAGE: "Done\nin 5 min",
        },
        blocking=True,
    )
    assert wall.last_call == (
        "POST",
        "/note",
        {"line1": "Laundry", "line2": "Done in 5 min"},
    )


async def test_send_message_without_width(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Without note.max the panel width of 21 characters applies."""
    wall.state["note"]["max"] = None
    await tick(hass, frozen_clock, 15)
    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MESSAGE: "The washing machine has finished"},
        blocking=True,
    )
    assert wall.last_call[2] == {
        "line1": "The washing machine",
        "line2": "has finished",
    }
