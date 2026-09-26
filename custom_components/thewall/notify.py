"""Send a note to the panel with notify.send_message."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NOTE_MAX_DEFAULT
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .entity import TheWallEntity

PARALLEL_UPDATES = 1


def wrap_note(message: str, width: int) -> tuple[str, str]:
    """Break a message into at most two lines of `width` characters.

    Lines break between words. A word longer than a line is cut into pieces.
    Whatever does not fit into two lines is left out.
    """
    lines: list[str] = []
    current = ""
    for word in message.split():
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = [*lines[:2], "", ""]
    return lines[0], lines[1]


def _one_line(text: str) -> str:
    """Join all whitespace into single spaces, the panel has no line breaks."""
    return " ".join(text.split())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TheWallConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the note notifier."""
    async_add_entities([TheWallNoteNotify(entry.runtime_data)])


class TheWallNoteNotify(TheWallEntity, NotifyEntity):
    """A message becomes the note. With a title, the title is line 1."""

    _attr_translation_key = "note"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, coordinator: TheWallCoordinator) -> None:
        """Create the notifier."""
        super().__init__(coordinator, "note")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Show the message on the panel."""
        if title:
            line1, line2 = _one_line(title), _one_line(message)
        else:
            width = self.note.get("max")
            if not isinstance(width, int) or width <= 0:
                width = NOTE_MAX_DEFAULT
            line1, line2 = wrap_note(message, width)
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.set_note(line1, line2))
