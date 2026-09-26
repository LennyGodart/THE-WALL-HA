"""Binary sensors: online, ringing, timer running."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 0


def _online(data: dict[str, Any]) -> bool:
    device = data.get("device")
    return bool(isinstance(device, dict) and device.get("online"))


def _timer_running(data: dict[str, Any]) -> bool:
    timers = data.get("timers")
    if not isinstance(timers, list):
        return False
    return any(isinstance(t, dict) and not t.get("ringing") for t in timers)


@dataclass(frozen=True, kw_only=True)
class TheWallBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor and how to read it from the state."""

    value_fn: Callable[[dict[str, Any]], bool]


BINARY_SENSORS: tuple[TheWallBinarySensorDescription, ...] = (
    TheWallBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_online,
    ),
    TheWallBinarySensorDescription(
        key="ringing",
        translation_key="ringing",
        value_fn=lambda data: bool(data.get("ringing")),
    ),
    TheWallBinarySensorDescription(
        key="timer_running",
        translation_key="timer_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_timer_running,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        TheWallBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class TheWallBinarySensor(TheWallEntity, BinarySensorEntity):
    """A yes or no from the state."""

    entity_description: TheWallBinarySensorDescription

    def __init__(
        self,
        coordinator: TheWallCoordinator,
        description: TheWallBinarySensorDescription,
    ) -> None:
        """Create the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.data)
