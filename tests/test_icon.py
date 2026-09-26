"""The brand icon: present, right size, made by tools/make_icon.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from PIL import Image, ImageChops
import pytest

ROOT = Path(__file__).parent.parent
BRAND = ROOT / "custom_components" / "thewall" / "brand"


def load_tool() -> ModuleType:
    """Import tools/make_icon.py, which is not a package."""
    spec = importlib.util.spec_from_file_location(
        "make_icon", ROOT / "tools" / "make_icon.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("name", "size"), [("icon.png", 256), ("icon@2x.png", 512)])
def test_icon_files(name: str, size: int) -> None:
    """Both sizes exist, match the generator and use the brand colors."""
    tool = load_tool()
    image = Image.open(BRAND / name).convert("RGB")
    assert image.size == (size, size)

    expected = tool.draw(size // 256, tool.FALLBACK_GLYPHS)
    _low, high = zip(*ImageChops.difference(image, expected).getextrema(), strict=True)
    assert max(high) <= 2, "run python tools/make_icon.py"

    scale = size // 256
    # Top left corner between grid dots is background.
    assert image.getpixel((0, 0)) == tool.BACKGROUND
    # The first LED of T sits in the middle of an amber dot.
    leds, columns, rows = tool.led_positions(tool.FALLBACK_GLYPHS)
    column, row = leds[0]
    left = (256 - ((columns - 1) * tool.LED_PITCH + 2 * tool.LED_RADIUS)) / 2
    top = (256 - ((rows - 1) * tool.LED_PITCH + 2 * tool.LED_RADIUS)) / 2
    x = int((left + tool.LED_RADIUS + column * tool.LED_PITCH) * scale)
    y = int((top + tool.LED_RADIUS + row * tool.LED_PITCH) * scale)
    assert image.getpixel((x, y)) == tool.AMBER


def test_fallback_matches_firmware_font() -> None:
    """The copy of the letters equals the firmware font, when it is there."""
    glyphs_h = ROOT.parent / "firmware" / "src" / "glyphs.h"
    if not glyphs_h.is_file():
        pytest.skip("firmware/src/glyphs.h is only in the private repository")
    tool = load_tool()
    font = tool.read_glyphs(glyphs_h)
    for char, rows in tool.FALLBACK_GLYPHS.items():
        assert font[char] == rows, char


def test_layout() -> None:
    """THE is centered above WALL, 23 by 17 LEDs."""
    tool = load_tool()
    leds, columns, rows = tool.led_positions(tool.FALLBACK_GLYPHS)
    assert (columns, rows) == (23, 17)
    the = [led for led in leds if led[1] < 7]
    wall = [led for led in leds if led[1] >= 10]
    assert min(c for c, _ in the) == 3
    assert max(c for c, _ in the) == 19
    assert min(c for c, _ in wall) == 0
    assert max(c for c, _ in wall) == 22
