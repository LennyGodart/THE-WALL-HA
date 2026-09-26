"""The mode of the panel."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Add the mode select."""
    async_add_entities([TheWallModeSelect(entry.runtime_data)])


class TheWallModeSelect(TheWallEntity, SelectEntity):
    """Pick the mode. Options are the mode IDs the server offers."""

    _attr_translation_key = "mode"

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the select."""
        super().__init__(coordinator, "mode")

    @property
    def options(self) -> list[str]:
        """Return the available modes."""
        return [
            mode["id"]
            for mode in self.panel.get("modes") or []
            if isinstance(mode, dict) and isinstance(mode.get("id"), str)
        ]

    @property
    def current_option(self) -> str | None:
        """Return the selected mode."""
        mode = self.panel.get("mode")
        return mode if isinstance(mode, str) else None

    async def async_select_option(self, option: str) -> None:
        """Switch to another mode."""
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.set_panel(mode=option))
