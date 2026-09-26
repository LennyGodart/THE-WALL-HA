"""Firmware of the device."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
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
    """Add the firmware update."""
    async_add_entities([TheWallFirmwareUpdate(entry.runtime_data)])


class TheWallFirmwareUpdate(TheWallEntity, UpdateEntity):
    """Install asks the device for the newest firmware.

    The device installs it on its next poll and restarts, so the update shows
    as in progress as long as the server reports the request as open.
    """

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the update entity."""
        super().__init__(coordinator, "firmware")

    @property
    def installed_version(self) -> str | None:
        """Return the firmware on the device."""
        fw = self.device.get("fw")
        return fw if isinstance(fw, str) and fw else None

    @property
    def latest_version(self) -> str | None:
        """Return the newest firmware, or the installed one if none is newer."""
        latest = self.device.get("fw_latest")
        if isinstance(latest, str) and latest:
            return latest
        return self.installed_version

    @property
    def in_progress(self) -> bool:
        """Return True while the device has not picked up the request."""
        return bool(self.device.get("fw_requested"))

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Ask the device to install the newest firmware."""
        client = self.coordinator.client
        await self.coordinator.async_command(client.update_firmware)
