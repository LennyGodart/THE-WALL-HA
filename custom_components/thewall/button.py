"""Buttons: hide the note, stop ringing, cancel or start timers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import TIMER_MAX_SECONDS
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 1


def _start_timer(coordinator: TheWallCoordinator) -> Awaitable[dict[str, Any]]:
    """Start a timer with the duration of the number entity."""
    seconds = max(1, min(TIMER_MAX_SECONDS, round(coordinator.timer_minutes * 60)))
    return coordinator.client.start_timer(seconds)


@dataclass(frozen=True, kw_only=True)
class TheWallButtonDescription(ButtonEntityDescription):
    """A button and the command it sends."""

    press_fn: Callable[[TheWallCoordinator], Awaitable[dict[str, Any]]]


BUTTONS: tuple[TheWallButtonDescription, ...] = (
    TheWallButtonDescription(
        key="hide_note",
        translation_key="hide_note",
        press_fn=lambda coordinator: coordinator.client.hide_note(),
    ),
    TheWallButtonDescription(
        key="stop_ringing",
        translation_key="stop_ringing",
        press_fn=lambda coordinator: coordinator.client.stop_ringing(),
    ),
    TheWallButtonDescription(
        key="cancel_timers",
        translation_key="cancel_timers",
        press_fn=lambda coordinator: coordinator.client.cancel_timer(),
    ),
    TheWallButtonDescription(
        key="start_timer",
        translation_key="start_timer",
        press_fn=_start_timer,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        TheWallButton(coordinator, description) for description in BUTTONS
    )


class TheWallButton(TheWallEntity, ButtonEntity):
    """A button that sends one command."""

    entity_description: TheWallButtonDescription

    def __init__(
        self, coordinator: TheWallCoordinator, description: TheWallButtonDescription
    ) -> None:
        """Create the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Send the command."""
        await self.coordinator.async_command(
            lambda: self.entity_description.press_fn(self.coordinator)
        )
