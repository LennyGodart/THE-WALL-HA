"""The voice blueprint loads, validates and maps spoken words to modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import load_yaml
import pytest

BLUEPRINT = Path(__file__).parent.parent / "blueprints" / "thewall_voice_modes.yaml"
OPTIONS = ["flight", "clock", "weather", "transit", "spotify", "notes"]


def automation_config() -> dict[str, Any]:
    """The automation the blueprint makes for select.wall_mode."""
    blueprint = Blueprint(
        load_yaml(str(BLUEPRINT)),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    assert set(blueprint.inputs) == {"mode_select"}
    inputs = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": "thewall/thewall_voice_modes.yaml",
                "input": {"mode_select": "select.wall_mode"},
            }
        },
    )
    inputs.validate()
    return inputs.async_substitute()


async def test_blueprint_is_valid(hass: HomeAssistant) -> None:
    """HA accepts the blueprint and the automation it produces.

    Runs inside the event loop, HA validates templates only there. The
    sentences themselves need hassil, which the test environment lacks.
    """
    config = automation_config()
    assert config["triggers"][0]["trigger"] == "conversation"
    validated = PLATFORM_SCHEMA(config)
    trigger = validated["triggers"][0]
    # The schema stores the trigger type under its old key.
    assert trigger["platform"] == "conversation"
    assert "show [the] {wall_mode} on the wall" in trigger["command"]
    assert "zeig[e] [den|die|das] {wall_mode} an der Wand" in trigger["command"]
    select = validated["actions"][0]["then"][0]
    assert select["action"] == "select.select_option"
    assert select["target"] == {"entity_id": ["select.wall_mode"]}


@pytest.mark.parametrize(
    ("spoken", "sentence", "mode", "german"),
    [
        ("clock", "show the clock on the wall", "clock", False),
        ("Flight Radar", "show the flight radar on the wall", "flight", False),
        ("planes", "put planes on the wall", "flight", False),
        ("Wetter", "zeig das Wetter an der Wand", "weather", True),
        ("Flugzeuge", "zeige die Flugzeuge an der Wand", "flight", True),
        ("Nahverkehr", "stell die Wand auf Nahverkehr", "transit", True),
        ("Musik ", "stell die Wand auf Musik", "spotify", True),
        ("Kaffee", "zeig den Kaffee an der Wand", "", True),
    ],
)
async def test_word_to_mode(
    hass: HomeAssistant, spoken: str, sentence: str, mode: str, german: bool
) -> None:
    """The templates turn the spoken word into a mode ID and pick the language."""
    variables = automation_config()["variables"]
    trigger = {"slots": {"wall_mode": spoken}, "sentence": sentence}
    wall_mode = Template(variables["wall_mode"], hass).async_render(
        {"trigger": trigger}
    )
    assert wall_mode == mode
    assert (
        Template(variables["german"], hass).async_render({"trigger": trigger}) is german
    )

    hass.states.async_set("select.wall_mode", "flight", {"options": OPTIONS})
    condition = automation_config()["actions"][0]["if"][0]["value_template"]
    known = Template(condition, hass).async_render(
        {"wall_mode": wall_mode, "mode_select": "select.wall_mode"}
    )
    assert known is bool(mode)
