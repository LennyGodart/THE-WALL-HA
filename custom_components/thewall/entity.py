"""Base entity for THE WALL."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import TheWallCoordinator, configuration_url


class TheWallEntity(CoordinatorEntity[TheWallCoordinator]):
    """One entity of one device, named by translation key."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TheWallCoordinator, key: str) -> None:
        """Attach the entity to the device of the config entry."""
        super().__init__(coordinator)
        uid = coordinator.uid
        device = coordinator.data.get("device") or {}
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=device.get("name") or uid,
            manufacturer=MANUFACTURER,
            model=device.get("model"),
            serial_number=uid,
            sw_version=device.get("fw"),
            configuration_url=configuration_url(device),
        )

    def _part(self, name: str) -> dict[str, Any]:
        """Return one object of the state, or an empty one."""
        value = self.coordinator.data.get(name)
        return value if isinstance(value, dict) else {}

    @property
    def device(self) -> dict[str, Any]:
        """The device part of the state."""
        return self._part("device")

    @property
    def panel(self) -> dict[str, Any]:
        """The panel part of the state."""
        return self._part("panel")

    @property
    def note(self) -> dict[str, Any]:
        """The note part of the state."""
        return self._part("note")

    @property
    def alarm(self) -> dict[str, Any]:
        """The alarm part of the state."""
        return self._part("alarm")

    @property
    def timers(self) -> list[dict[str, Any]]:
        """All timers, sorted by end."""
        timers = self.coordinator.data.get("timers")
        if not isinstance(timers, list):
            return []
        return [timer for timer in timers if isinstance(timer, dict)]
