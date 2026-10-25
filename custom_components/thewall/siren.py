"""Siren: let the wall beep like a timer that ran out, and stop it again."""

from __future__ import annotations

from typing import Any

from homeassistant.components.siren import (
    ATTR_DURATION,
    SirenEntity,
    SirenEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BEEP_MAX_SECONDS
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the beep siren."""
    async_add_entities([TheWallBeepSiren(entry.runtime_data)])


class TheWallBeepSiren(TheWallEntity, SirenEntity):
    """Beeping started from Home Assistant.

    The wall rings like a timer that ran out, with HOME ASSISTANT on the panel,
    for the duration or until someone stops it, 15 minutes at most like any
    ringing. It beeps even when the sound switch is off, that switch is for
    timers and the alarm. Ringing timers and the alarm are not the siren: turning
    it off leaves them alone, the stop ringing button ends everything.
    """

    _attr_translation_key = "beep"
    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
    )

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the siren."""
        super().__init__(coordinator, "beep")

    @property
    def available(self) -> bool:
        """Return False when the server cannot make the wall beep."""
        return super().available and isinstance(self.coordinator.data.get("beep"), dict)

    @property
    def is_on(self) -> bool:
        """Return whether the wall beeps for Home Assistant."""
        return bool(self._part("beep").get("on"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Beep for the duration in seconds, or until stopped.

        Longer than the 15 minutes any ringing lasts is cut to them.
        """
        duration = kwargs.get(ATTR_DURATION)
        seconds = (
            None if duration is None else max(1, min(BEEP_MAX_SECONDS, int(duration)))
        )
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.beep(True, seconds))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the beeping."""
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.beep(False))
