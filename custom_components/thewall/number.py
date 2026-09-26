"""Duration for the "Start timer" button. Stored in Home Assistant only."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import TIMER_MAX_MINUTES
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the timer duration."""
    async_add_entities([TheWallTimerDuration(entry.runtime_data)])


class TheWallTimerDuration(TheWallEntity, RestoreNumber):
    """Minutes, 1 to 240. Survives restarts, never sent to the server."""

    _attr_translation_key = "timer_duration"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 1
    _attr_native_max_value = TIMER_MAX_MINUTES
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the number with the default duration."""
        super().__init__(coordinator, "timer_duration")
        self._attr_native_value = coordinator.timer_minutes

    @property
    def available(self) -> bool:
        """Always available, the value lives in Home Assistant."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last duration."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is None or last.native_value is None:
            return
        value = max(1.0, min(float(TIMER_MAX_MINUTES), float(last.native_value)))
        self._attr_native_value = value
        self.coordinator.timer_minutes = value

    async def async_set_native_value(self, value: float) -> None:
        """Keep the new duration."""
        self._attr_native_value = value
        self.coordinator.timer_minutes = value
        self.async_write_ha_state()
