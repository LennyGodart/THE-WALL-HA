"""Sensors: timer, alarm, what the panel shows, the aircraft, diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfLength,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import KNOWN_MODES, SHOWING_SPECIAL
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 0


def _part(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return dt_util.utc_from_timestamp(value)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _running_timers(data: dict[str, Any]) -> list[dict[str, Any]]:
    timers = data.get("timers")
    if not isinstance(timers, list):
        return []
    return [t for t in timers if isinstance(t, dict) and not t.get("ringing")]


def _next_timer_end(data: dict[str, Any]) -> datetime | None:
    running = _running_timers(data)
    return _timestamp(running[0].get("end")) if running else None


def _timer_attributes(data: dict[str, Any]) -> dict[str, Any]:
    running = _running_timers(data)
    if not running:
        return {"count": 0}
    timer = running[0]
    return {
        "timer_id": timer.get("id"),
        "label": _text(timer.get("label")),
        "total": timer.get("total"),
        "count": len(running),
    }


def _next_alarm(data: dict[str, Any]) -> datetime | None:
    alarm = _part(data, "alarm")
    return _timestamp(alarm.get("next")) if alarm.get("on") else None


def _route(data: dict[str, Any]) -> str | None:
    flight = _part(data, "flight")
    origin, destination = _text(flight.get("from")), _text(flight.get("to"))
    if origin and destination:
        return f"{origin} - {destination}"
    return None


def _route_attributes(data: dict[str, Any]) -> dict[str, Any]:
    flight = _part(data, "flight")
    return {
        "from": _text(flight.get("from")),
        "to": _text(flight.get("to")),
        "from_city": _text(flight.get("from_city")),
        "to_city": _text(flight.get("to_city")),
    }


def _callsign_attributes(data: dict[str, Any]) -> dict[str, Any]:
    flight = _part(data, "flight")
    return {
        "registration": _text(flight.get("reg")),
        "icao24": _text(flight.get("hex")),
    }


def _airline_attributes(data: dict[str, Any]) -> dict[str, Any]:
    return {"icao": _text(_part(data, "flight").get("airline_icao"))}


def _flight_value(
    key: str, convert: Callable[[Any], Any]
) -> Callable[[dict[str, Any]], Any]:
    return lambda data: convert(_part(data, "flight").get(key))


@dataclass(frozen=True, kw_only=True)
class TheWallSensorDescription(SensorEntityDescription):
    """A sensor and how to read it from the state."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[TheWallSensorDescription, ...] = (
    TheWallSensorDescription(
        key="timer",
        translation_key="timer",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_timer_end,
        attributes_fn=_timer_attributes,
    ),
    TheWallSensorDescription(
        key="next_alarm",
        translation_key="next_alarm",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_alarm,
    ),
    TheWallSensorDescription(
        key="callsign",
        translation_key="callsign",
        value_fn=_flight_value("callsign", _text),
        attributes_fn=_callsign_attributes,
    ),
    TheWallSensorDescription(
        key="airline",
        translation_key="airline",
        value_fn=_flight_value("airline", _text),
        attributes_fn=_airline_attributes,
    ),
    TheWallSensorDescription(
        key="aircraft_type",
        translation_key="aircraft_type",
        value_fn=_flight_value("type", _text),
    ),
    TheWallSensorDescription(
        key="altitude",
        translation_key="altitude",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.FEET,
        # Aviation units stay the default, also in a metric Home Assistant.
        suggested_unit_of_measurement=UnitOfLength.FEET,
        suggested_display_precision=0,
        value_fn=_flight_value("alt_ft", _number),
    ),
    TheWallSensorDescription(
        key="ground_speed",
        translation_key="ground_speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        suggested_display_precision=0,
        value_fn=_flight_value("speed_kt", _number),
    ),
    TheWallSensorDescription(
        key="distance",
        translation_key="distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.NAUTICAL_MILES,
        suggested_unit_of_measurement=UnitOfLength.NAUTICAL_MILES,
        suggested_display_precision=1,
        value_fn=_flight_value("dist_nm", _number),
    ),
    TheWallSensorDescription(
        key="route",
        translation_key="route",
        value_fn=_route,
        attributes_fn=_route_attributes,
    ),
    TheWallSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _timestamp(_part(data, "device").get("last_seen")),
    ),
    TheWallSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: _number(_part(data, "device").get("rssi")),
    ),
)

SHOWING = TheWallSensorDescription(
    key="showing",
    translation_key="showing",
    device_class=SensorDeviceClass.ENUM,
    value_fn=lambda data: _text(_part(data, "panel").get("showing")),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    entities: list[TheWallSensor] = [
        TheWallSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(TheWallShowingSensor(coordinator, SHOWING))
    async_add_entities(entities)


class TheWallSensor(TheWallEntity, SensorEntity):
    """A value from the state."""

    entity_description: TheWallSensorDescription

    def __init__(
        self, coordinator: TheWallCoordinator, description: TheWallSensorDescription
    ) -> None:
        """Create the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra details, where there are any."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class TheWallShowingSensor(TheWallSensor):
    """What the panel shows right now: a mode, or ring, pairing, hello, off."""

    @property
    def options(self) -> list[str]:
        """Return every value the sensor can take.

        Modes newer than this integration and values the server adds later
        are appended, so the state never falls outside the list.
        """
        options = [*KNOWN_MODES, *SHOWING_SPECIAL]
        panel = _part(self.coordinator.data, "panel")
        for mode in panel.get("modes") or []:
            if (
                isinstance(mode, dict)
                and isinstance(mode.get("id"), str)
                and mode["id"] not in options
            ):
                options.append(mode["id"])
        showing = _text(panel.get("showing"))
        if showing and showing not in options:
            options.append(showing)
        return options
