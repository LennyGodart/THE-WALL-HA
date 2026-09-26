"""Sensors: timer, alarm, showing, the aircraft, diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_OPTIONS, SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import METRIC_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import NOW_TS, tick
from .fake_server import FakeWall

FLIGHT_SENSORS = (
    "sensor.wall_callsign",
    "sensor.wall_airline",
    "sensor.wall_aircraft_type",
    "sensor.wall_altitude",
    "sensor.wall_ground_speed",
    "sensor.wall_distance",
    "sensor.wall_route",
)


def iso(timestamp: int) -> str:
    """A unix time the way timestamp sensors show it."""
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


@pytest.mark.parametrize(
    ("entity_id", "value"),
    [
        ("sensor.wall_timer", iso(NOW_TS + 300)),
        ("sensor.wall_next_alarm", STATE_UNKNOWN),
        ("sensor.wall_showing", "flight"),
        ("sensor.wall_callsign", "LGL4KP"),
        ("sensor.wall_airline", "LUXAIR"),
        ("sensor.wall_aircraft_type", "Dash 8-400"),
        ("sensor.wall_altitude", "11000"),
        ("sensor.wall_ground_speed", "280"),
        ("sensor.wall_distance", "12.3"),
        ("sensor.wall_route", "LUX - MUC"),
        ("sensor.wall_last_seen", iso(NOW_TS - 5)),
    ],
)
async def test_values(
    hass: HomeAssistant, init_integration: MockConfigEntry, entity_id: str, value: str
) -> None:
    """Every sensor reads its part of the state."""
    assert hass.states.get(entity_id).state == value


async def test_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Details that do not fit into the state."""
    timer = hass.states.get("sensor.wall_timer").attributes
    assert timer["timer_id"] == "a1b2c3d4"
    assert timer["label"] == "Pasta"
    assert timer["total"] == 300
    assert timer["count"] == 1
    assert timer[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP

    route = hass.states.get("sensor.wall_route").attributes
    assert route["from"] == "LUX"
    assert route["to"] == "MUC"
    assert route["from_city"] == "Luxembourg"
    assert route["to_city"] == "Munich"

    callsign = hass.states.get("sensor.wall_callsign").attributes
    assert callsign["registration"] == "LX-LQA"
    assert callsign["icao24"] == "4d0123"
    assert hass.states.get("sensor.wall_airline").attributes["icao"] == "LGL"


async def test_aviation_units_in_metric(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Feet, knots and nautical miles stay, also in a metric Home Assistant."""
    assert hass.config.units is METRIC_SYSTEM
    expected = {
        "sensor.wall_altitude": ("ft", SensorDeviceClass.DISTANCE),
        "sensor.wall_ground_speed": ("kn", SensorDeviceClass.SPEED),
        "sensor.wall_distance": ("nmi", SensorDeviceClass.DISTANCE),
    }
    for entity_id, (unit, device_class) in expected.items():
        attributes = hass.states.get(entity_id).attributes
        assert attributes[ATTR_UNIT_OF_MEASUREMENT] == unit
        assert attributes[ATTR_DEVICE_CLASS] == device_class


async def test_showing_options(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Modes plus ring, pairing, hello and off."""
    state = hass.states.get("sensor.wall_showing")
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENUM
    assert state.attributes[ATTR_OPTIONS] == [
        "flight",
        "clock",
        "weather",
        "transit",
        "spotify",
        "notes",
        "ring",
        "pairing",
        "hello",
        "off",
    ]


async def test_showing_new_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """New modes and unknown values join the options instead of failing."""
    wall.state["panel"]["modes"].append(
        {"id": "pixel", "en": "Pixel editor", "de": "Pixel-Editor", "rotatable": True}
    )
    wall.state["panel"]["showing"] = "screensaver"
    await tick(hass, frozen_clock, 15)
    state = hass.states.get("sensor.wall_showing")
    assert state.state == "screensaver"
    assert state.attributes[ATTR_OPTIONS][-2:] == ["pixel", "screensaver"]


async def test_no_flight(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Without an aircraft on the panel the flight sensors are unknown."""
    wall.state["flight"] = None
    await tick(hass, frozen_clock, 15)
    for entity_id in FLIGHT_SENSORS:
        assert hass.states.get(entity_id).state == STATE_UNKNOWN, entity_id
    assert hass.states.get("sensor.wall_route").attributes["from"] is None


async def test_partial_flight(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """Missing fields leave just those sensors unknown."""
    wall.state["flight"].update(to=None, alt_ft=None, airline="")
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("sensor.wall_route").state == STATE_UNKNOWN
    assert hass.states.get("sensor.wall_altitude").state == STATE_UNKNOWN
    assert hass.states.get("sensor.wall_airline").state == STATE_UNKNOWN
    assert hass.states.get("sensor.wall_callsign").state == "LGL4KP"


async def test_next_alarm(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """The next alarm shows only while the alarm is on."""
    wall.state["alarm"]["on"] = True
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("sensor.wall_next_alarm").state == iso(1790050000)

    wall.state["alarm"]["next"] = None
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("sensor.wall_next_alarm").state == STATE_UNKNOWN


async def test_timer_without_timers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """No running timer: unknown, count 0."""
    wall.state["timers"] = []
    await tick(hass, frozen_clock, 15)
    state = hass.states.get("sensor.wall_timer")
    assert state.state == STATE_UNKNOWN
    assert state.attributes["count"] == 0
    assert "label" not in state.attributes


async def test_timer_skips_ringing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """A ringing timer is over, the sensor shows the next running one."""
    wall.state["timers"].append(
        {"id": "e5f6", "label": "", "total": 600, "end": NOW_TS + 600, "ringing": False}
    )
    await tick(hass, frozen_clock, 301)
    state = hass.states.get("sensor.wall_timer")
    assert state.state == iso(NOW_TS + 600)
    assert state.attributes["timer_id"] == "e5f6"
    assert state.attributes["label"] is None
    assert state.attributes["count"] == 1


async def test_diagnostic_sensors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Last seen is on, the WiFi signal is off by default."""
    last_seen = entity_registry.async_get("sensor.wall_last_seen")
    assert last_seen.entity_category is EntityCategory.DIAGNOSTIC
    assert last_seen.disabled_by is None
    wifi = entity_registry.async_get("sensor.wall_wifi_signal")
    assert wifi.entity_category is EntityCategory.DIAGNOSTIC
    assert wifi.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_wifi_signal(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """RSSI in dBm."""
    state = hass.states.get("sensor.wall_wifi_signal")
    assert state.state == "-54"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "dBm"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.SIGNAL_STRENGTH


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_nullable_device_fields(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    wall: FakeWall,
    frozen_clock: FrozenDateTimeFactory,
) -> None:
    """last_seen and rssi may be null."""
    wall.state["device"].update(last_seen=None, rssi=None)
    await tick(hass, frozen_clock, 15)
    assert hass.states.get("sensor.wall_last_seen").state == STATE_UNKNOWN
    assert hass.states.get("sensor.wall_wifi_signal").state == STATE_UNKNOWN
