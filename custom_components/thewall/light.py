"""The whole panel as a light: on, off and brightness."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
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
    """Add the panel light."""
    async_add_entities([TheWallPanelLight(entry.runtime_data)])


class TheWallPanelLight(TheWallEntity, LightEntity):
    """The panel. Brightness maps 1:1 to the server value 1 to 255."""

    # Main feature of the device, so the entity takes the device name.
    _attr_name = None
    _attr_translation_key = "panel"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the light."""
        super().__init__(coordinator, "panel")

    @property
    def is_on(self) -> bool:
        """Return whether the panel is on."""
        return bool(self.panel.get("on"))

    @property
    def brightness(self) -> int | None:
        """Return the brightness, 1 to 255."""
        bright = self.panel.get("bright")
        return bright if isinstance(bright, int) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the panel on, with a brightness if one was given."""
        bright: int | None = None
        if ATTR_BRIGHTNESS in kwargs:
            bright = max(1, min(255, int(kwargs[ATTR_BRIGHTNESS])))
        client = self.coordinator.client
        await self.coordinator.async_command(
            lambda: client.set_panel(on=True, bright=bright)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the panel off."""
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.set_panel(on=False))
