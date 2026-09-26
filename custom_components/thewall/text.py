"""The two lines of the note."""

from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NOTE_MAX_DEFAULT
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

# One at a time: each line sends the other one along, so a second change must
# see the state the first one returned.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add both note lines."""
    coordinator = entry.runtime_data
    async_add_entities(
        [TheWallNoteLine(coordinator, 1), TheWallNoteLine(coordinator, 2)]
    )


class TheWallNoteLine(TheWallEntity, TextEntity):
    """One line of the note. Changing it keeps the other line."""

    _attr_mode = TextMode.TEXT
    _attr_native_min = 0

    def __init__(self, coordinator: TheWallCoordinator, line: int) -> None:
        """Create the entity for line 1 or 2."""
        super().__init__(coordinator, f"note_line{line}")
        self._attr_translation_key = f"note_line{line}"
        self._line = f"line{line}"
        self._other = "line2" if line == 1 else "line1"

    @property
    def native_max(self) -> int:
        """Return how many characters fit on the panel."""
        value = self.note.get("max")
        return value if isinstance(value, int) and value > 0 else NOTE_MAX_DEFAULT

    @property
    def native_value(self) -> str | None:
        """Return the line."""
        value = self.note.get(self._line)
        if not isinstance(value, str):
            return None
        return value[: self.native_max]

    async def async_set_value(self, value: str) -> None:
        """Send the note with this line replaced."""

        async def _command() -> dict[str, Any]:
            lines = {
                self._line: value,
                self._other: str(self.note.get(self._other) or ""),
            }
            return await self.coordinator.client.set_note(
                lines["line1"], lines["line2"]
            )

        await self.coordinator.async_command(_command)
