"""Timer events: started, finished, cancelled."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import TIMER_EVENT_CANCELLED, TIMER_EVENT_FINISHED, TIMER_EVENT_STARTED
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the timer event."""
    async_add_entities([TheWallTimerEvent(entry.runtime_data)])


def _attributes(timer: dict[str, Any]) -> dict[str, Any]:
    """Event data for one timer."""
    label = timer.get("label")
    return {
        "timer_id": timer.get("id"),
        "label": label if isinstance(label, str) and label else None,
        "total": timer.get("total"),
    }


class TheWallTimerEvent(TheWallEntity, EventEntity):
    """Compares the timers of two states and fires what changed.

    started: a timer is new. finished: a timer rings, or it disappeared after
    its end without being seen ringing. cancelled: a timer disappeared before
    its end. A ringing timer that is dismissed fires nothing more.
    """

    _attr_translation_key = "timer"
    _attr_event_types = [
        TIMER_EVENT_STARTED,
        TIMER_EVENT_FINISHED,
        TIMER_EVENT_CANCELLED,
    ]

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the event entity.

        Timers that already run at this point are the starting point, they
        fire nothing.
        """
        super().__init__(coordinator, "timer")
        self._known = self._current()

    def _current(self) -> dict[str, dict[str, Any]]:
        """Timers of the current state by ID."""
        return {
            timer["id"]: timer
            for timer in self.timers
            if isinstance(timer.get("id"), str)
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire events for the changes, then write the state as usual."""
        if self.coordinator.last_update_success:
            self._fire_changes()
        super()._handle_coordinator_update()

    @callback
    def _fire_changes(self) -> None:
        """Compare with the last known timers."""
        now = self.coordinator.data.get("time")
        if not isinstance(now, int | float):
            now = time.time()
        current = self._current()
        previous, self._known = self._known, current
        events: list[tuple[str, dict[str, Any]]] = []
        for timer_id, old in previous.items():
            new = current.get(timer_id)
            if new is None:
                if old.get("ringing"):
                    continue
                end = old.get("end")
                ended = isinstance(end, int | float) and end <= now
                events.append(
                    (TIMER_EVENT_FINISHED if ended else TIMER_EVENT_CANCELLED, old)
                )
            elif new.get("ringing") and not old.get("ringing"):
                events.append((TIMER_EVENT_FINISHED, new))
        for timer_id, new in current.items():
            if timer_id not in previous:
                events.append((TIMER_EVENT_STARTED, new))
                if new.get("ringing"):
                    events.append((TIMER_EVENT_FINISHED, new))
        for event_type, timer in events:
            self._trigger_event(event_type, _attributes(timer))
            self.async_write_ha_state()
