"""Timer events from the difference between two states."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientConnectionError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.const import ATTR_ENTITY_ID, EVENT_STATE_CHANGED, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.thewall.const import DOMAIN

from .conftest import NOW_TS, tick
from .fake_server import FakeWall

ENTITY_ID = "event.wall_timer"


def record(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Collect every event the entity fires, in order."""
    fired: list[dict[str, Any]] = []

    @callback
    def _listener(event: Event) -> None:
        if event.data["entity_id"] != ENTITY_ID:
            return
        new = event.data["new_state"]
        if new is None or new.state in (STATE_UNKNOWN, "unavailable"):
            return
        if event.data["old_state"] and event.data["old_state"].state == new.state:
            return
        fired.append(
            {
                "type": new.attributes[ATTR_EVENT_TYPE],
                "timer_id": new.attributes["timer_id"],
                "label": new.attributes["label"],
                "total": new.attributes["total"],
            }
        )

    hass.bus.async_listen(EVENT_STATE_CHANGED, _listener)
    return fired


async def press(hass: HomeAssistant, entity_id: str) -> None:
    """Press a button."""
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


async def test_no_event_at_start(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Timers that already run when Home Assistant starts fire nothing."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_EVENT_TYPES] == ["started", "finished", "cancelled"]


async def test_started(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """A new timer fires started, right from the command response."""
    fired = record(hass)
    await hass.services.async_call(
        DOMAIN,
        "start_timer",
        {"duration": {"minutes": 10}, "label": "Tea"},
        blocking=True,
    )
    assert fired == [
        {"type": "started", "timer_id": "t0000001", "label": "Tea", "total": 600}
    ]


async def test_finished(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A timer that rings fires finished once, dismissing it fires nothing."""
    fired = record(hass)
    await tick(hass, frozen_clock, 301)
    assert fired == [
        {"type": "finished", "timer_id": "a1b2c3d4", "label": "Pasta", "total": 300}
    ]

    await tick(hass, frozen_clock, 15)
    await press(hass, "button.wall_stop_ringing")
    assert len(fired) == 1


async def test_cancelled(
    hass: HomeAssistant, init_integration: MockConfigEntry, wall: FakeWall
) -> None:
    """A timer removed before its end fires cancelled."""
    fired = record(hass)
    await press(hass, "button.wall_cancel_timers")
    assert fired == [
        {"type": "cancelled", "timer_id": "a1b2c3d4", "label": "Pasta", "total": 300}
    ]


async def test_finished_between_polls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Gone after its end without being seen ringing still counts as finished."""
    fired = record(hass)
    wall.state["timers"] = []
    await tick(hass, frozen_clock, 301)
    assert [event["type"] for event in fired] == ["finished"]


async def test_started_and_finished_between_polls(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A short timer seen for the first time while ringing fires both, in order."""
    fired = record(hass)
    wall.state["timers"].append(
        {"id": "short", "label": "", "total": 5, "end": NOW_TS + 5, "ringing": False}
    )
    await tick(hass, frozen_clock, 15)
    assert fired == [
        {"type": "started", "timer_id": "short", "label": None, "total": 5},
        {"type": "finished", "timer_id": "short", "label": None, "total": 5},
    ]


async def test_changes_across_an_outage(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Changes during an outage are reported once the server answers again."""
    fired = record(hass)
    wall.respond("/state", exc=ClientConnectionError("down"))
    wall.state["timers"] = []
    await tick(hass, frozen_clock, 15)
    assert hass.states.get(ENTITY_ID).state == "unavailable"
    assert fired == []

    await tick(hass, frozen_clock, 15)
    assert [event["type"] for event in fired] == ["cancelled"]
