"""Draw the icon of THE WALL for Home Assistant.

Writes custom_components/thewall/brand/icon.png (256 x 256) and icon@2x.png
(512 x 512). Home Assistant 2026.3 and newer serves these files for custom
integrations from the brand folder, no pull request to the brands repository
is needed.

THE and WALL come from the 5 x 7 font of the panel in firmware/src/glyphs.h.
Every font pixel becomes one round amber LED, on the dark background with the
6 px dot grid of the website.

    python tools/make_icon.py [--glyphs path/to/glyphs.h]

The public repository has no firmware folder. There the script uses the copy
of the six letters below; tests/test_icon.py checks that the copy still
matches the firmware font whenever glyphs.h is at hand.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLYPHS = ROOT.parent / "firmware" / "src" / "glyphs.h"
BRAND = ROOT / "custom_components" / "thewall" / "brand"

BACKGROUND = (0x08, 0x09, 0x0A)
GRID = (0x18, 0x1C, 0x20)
AMBER = (0xFF, 0xAA, 0x00)

SIZE = 256  # at 1x
GRID_STEP = 6  # dot grid every 6 px at 1x, one dot in the middle of each cell
GRID_RADIUS = 1.1  # like the CSS: 1 px dot with a soft edge
LED_PITCH = 10  # one font pixel at 1x
LED_RADIUS = 4.0  # 8 px LEDs, 2 px apart
LINE_GAP = 3  # empty LED rows between THE and WALL
SUPERSAMPLE = 4
LINES = ("THE", "WALL")

# The letters as in firmware/src/glyphs.h: 7 rows of 5 bits, bit 4 is the
# left column.
FALLBACK_GLYPHS: dict[str, tuple[int, ...]] = {
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11),
}

_GLYPH = re.compile(r"\{0x([0-9A-Fa-f]{4}),\s*\{([^}]*)\}\}")


def read_glyphs(path: Path) -> dict[str, tuple[int, ...]]:
    """Read every glyph of the firmware font."""
    glyphs: dict[str, tuple[int, ...]] = {}
    for codepoint, rows in _GLYPH.findall(path.read_text(encoding="utf-8")):
        values = tuple(int(value, 16) for value in rows.split(","))
        if len(values) == 7:
            glyphs[chr(int(codepoint, 16))] = values
    return glyphs


def led_positions(
    glyphs: dict[str, tuple[int, ...]],
) -> tuple[list[tuple[int, int]], int, int]:
    """Lit LEDs as (column, row), THE centered above WALL.

    Returns the LEDs and the size of the block in LEDs. A character is 5
    columns wide with 1 empty column after it, as on the panel.
    """
    width = max(6 * len(line) - 1 for line in LINES)
    height = len(LINES) * 7 + (len(LINES) - 1) * LINE_GAP
    leds: list[tuple[int, int]] = []
    for index, line in enumerate(LINES):
        top = index * (7 + LINE_GAP)
        left = (width - (6 * len(line) - 1)) // 2
        for position, char in enumerate(line):
            for row, bits in enumerate(glyphs[char]):
                for column in range(5):
                    if bits & (0x10 >> column):
                        leds.append((left + 6 * position + column, top + row))
    return leds, width, height


def draw(scale: int, glyphs: dict[str, tuple[int, ...]]) -> Image.Image:
    """Draw the icon at 1x or 2x, supersampled for smooth dots."""
    factor = SUPERSAMPLE * scale
    size = SIZE * factor
    image = Image.new("RGB", (size, size), BACKGROUND)
    canvas = ImageDraw.Draw(image)

    step = GRID_STEP * factor
    radius = GRID_RADIUS * factor
    for y in range(step // 2, size, step):
        for x in range(step // 2, size, step):
            canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=GRID)

    leds, columns, rows = led_positions(glyphs)
    pitch = LED_PITCH * factor
    radius = LED_RADIUS * factor
    left = (size - ((columns - 1) * pitch + 2 * radius)) / 2 + radius
    top = (size - ((rows - 1) * pitch + 2 * radius)) / 2 + radius
    for column, row in leds:
        x, y = left + column * pitch, top + row * pitch
        canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=AMBER)

    return image.resize((SIZE * scale, SIZE * scale), Image.Resampling.LANCZOS)


def main() -> None:
    """Write both icons."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--glyphs", type=Path, default=DEFAULT_GLYPHS)
    args = parser.parse_args()

    if args.glyphs.is_file():
        glyphs = read_glyphs(args.glyphs)
        print(f"Font: {args.glyphs}")
    else:
        glyphs = FALLBACK_GLYPHS
        print(f"{args.glyphs} not found, using the copy in this script")

    BRAND.mkdir(parents=True, exist_ok=True)
    for scale, name in ((1, "icon.png"), (2, "icon@2x.png")):
        path = BRAND / name
        draw(scale, glyphs).save(path, optimize=True)
        print(f"Wrote {path.relative_to(ROOT)} ({SIZE * scale} x {SIZE * scale})")


if __name__ == "__main__":
    main()
