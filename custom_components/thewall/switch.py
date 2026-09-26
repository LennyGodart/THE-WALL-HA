"""Switches: the alarm, and one per mode that can be in the rotation."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import KNOWN_MODES
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 1


def rotatable_modes(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the modes of the state that can take part in the rotation."""
    panel = data.get("panel") or {}
    return [
        mode
        for mode in panel.get("modes") or []
        if isinstance(mode, dict)
        and isinstance(mode.get("id"), str)
        and mode.get("rotatable")
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the alarm switch and the rotation switches.

    A mode that becomes available later, for example once Spotify is set up,
    gets its switch without a reload.
    """
    coordinator = entry.runtime_data
    async_add_entities([TheWallAlarmSwitch(coordinator)])
    known: set[str] = set()

    @callback
    def _add_rotation_switches() -> None:
        new = [
            mode
            for mode in rotatable_modes(coordinator.data)
            if mode["id"] not in known
        ]
        if not new:
            return
        known.update(mode["id"] for mode in new)
        async_add_entities(TheWallRotationSwitch(coordinator, mode) for mode in new)

    _add_rotation_switches()
    entry.async_on_unload(coordinator.async_add_listener(_add_rotation_switches))


class TheWallAlarmSwitch(TheWallEntity, SwitchEntity):
    """The one alarm of the device."""

    _attr_translation_key = "alarm"

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the switch."""
        super().__init__(coordinator, "alarm")

    @property
    def is_on(self) -> bool:
        """Return whether the alarm is set."""
        return bool(self.alarm.get("on"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the alarm."""
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.set_alarm(on=True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the alarm."""
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.set_alarm(on=False))


class TheWallRotationSwitch(TheWallEntity, SwitchEntity):
    """Whether one mode is part of the rotation."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TheWallCoordinator, mode: dict[str, Any]) -> None:
        """Create the switch for one mode."""
        mode_id: str = mode["id"]
        super().__init__(coordinator, f"rotation_{mode_id}")
        self._mode = mode_id
        if mode_id in KNOWN_MODES:
            self._attr_translation_key = f"rotation_{mode_id}"
        else:
            # A mode newer than this integration: name it the way the server does.
            lang = "de" if coordinator.language.lower().startswith("de") else "en"
            self._attr_translation_key = "rotation_other"
            self._attr_translation_placeholders = {
                "mode": str(mode.get(lang) or mode.get("en") or mode_id)
            }

    @property
    def available(self) -> bool:
        """Return False once the server no longer offers the mode."""
        return super().available and any(
            mode["id"] == self._mode for mode in rotatable_modes(self.coordinator.data)
        )

    @property
    def is_on(self) -> bool:
        """Return whether the mode is in the rotation."""
        return self._mode in (self.panel.get("rotation") or [])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Add the mode to the end of the rotation."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Remove the mode from the rotation."""
        await self._async_set(False)

    async def _async_set(self, include: bool) -> None:
        """Send the whole rotation list with this mode added or removed."""

        async def _command() -> dict[str, Any]:
            # Read the list when the command runs, after earlier commands
            # returned their state, so two quick toggles do not undo each other.
            rotation = [
                mode for mode in self.panel.get("rotation") or [] if mode != self._mode
            ]
            if include:
                rotation.append(self._mode)
            return await self.coordinator.client.set_panel(rotation=rotation)

        await self.coordinator.async_command(_command)
