"""The alarm time."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the alarm time."""
    async_add_entities([TheWallAlarmTime(entry.runtime_data)])


def parse_hhmm(value: object) -> time | None:
    """Turn "07:00" into a time, anything else into None."""
    if not isinstance(value, str):
        return None
    hours, _, minutes = value.partition(":")
    try:
        return time(int(hours), int(minutes))
    except ValueError:
        return None


class TheWallAlarmTime(TheWallEntity, TimeEntity):
    """When the alarm rings, on the days set on the website."""

    _attr_translation_key = "alarm_time"

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the entity."""
        super().__init__(coordinator, "alarm_time")

    @property
    def native_value(self) -> time | None:
        """Return the alarm time."""
        return parse_hhmm(self.alarm.get("time"))

    async def async_set_value(self, value: time) -> None:
        """Set a new alarm time. Seconds are dropped, the panel has none."""
        hhmm = f"{value.hour:02d}:{value.minute:02d}"
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.set_alarm(time=hhmm))
