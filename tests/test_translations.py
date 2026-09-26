"""Translations, services.yaml, icons, manifest and the text rules of the project."""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import re
from typing import Any

import pytest
import yaml

from custom_components.thewall.config_flow import _PAIR_ERRORS
from custom_components.thewall.const import KNOWN_MODES
from custom_components.thewall.coordinator import _OWN_MESSAGE_CODES

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "custom_components" / "thewall"
EN = json.loads((PACKAGE / "translations" / "en.json").read_text(encoding="utf-8"))
DE = json.loads((PACKAGE / "translations" / "de.json").read_text(encoding="utf-8"))

PLATFORMS = (
    "binary_sensor",
    "button",
    "event",
    "light",
    "notify",
    "number",
    "select",
    "sensor",
    "switch",
    "text",
    "time",
    "update",
)
PLACEHOLDER = re.compile(r"\{(\w+)\}")
TRANSLATION_KEY = re.compile(r"translation_key=\"(\w+)\"")
# Machine-looking punctuation and phrases the project does not use.
FORBIDDEN_CHARACTERS = {chr(0x2014): "em dash", chr(0x2013): "en dash"}
EMOJI = re.compile(
    f"[{chr(0x1F300)}-{chr(0x1FAFF)}{chr(0x2600)}-{chr(0x27BF)}{chr(0x2B50)}{chr(0x2B55)}]"
)
FORBIDDEN_PHRASES = (
    "seamless",
    "elevate",
    "unleash",
    "next-gen",
    "nahtlos",
    "revolutionär",
    "effortless",
    "game changer",
)


def strings(
    tree: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], str]]:
    """Every string of a translation file with its key path."""
    if isinstance(tree, dict):
        for key, value in tree.items():
            yield from strings(value, (*path, key))
    else:
        yield path, tree


def text_files() -> list[Path]:
    """All files a person reads or ships."""
    files = [
        *ROOT.glob("*.md"),
        *ROOT.glob("*.json"),
        *ROOT.glob("blueprints/*.yaml"),
        *PACKAGE.rglob("*.json"),
        *PACKAGE.rglob("*.yaml"),
        *PACKAGE.rglob("*.py"),
        *ROOT.glob("tools/*.py"),
        *ROOT.glob("tests/*.py"),
    ]
    return sorted(set(files))


def test_same_keys_in_both_languages() -> None:
    """German is complete."""
    assert {path for path, _ in strings(EN)} == {path for path, _ in strings(DE)}


def test_same_placeholders_in_both_languages() -> None:
    """A placeholder in English is also in German, and the other way round."""
    german = dict(strings(DE))
    for path, text in strings(EN):
        assert set(PLACEHOLDER.findall(text)) == set(
            PLACEHOLDER.findall(german[path])
        ), path


def test_no_empty_strings() -> None:
    """Nothing is left blank."""
    for path, text in [*strings(EN), *strings(DE)]:
        assert isinstance(text, str), path
        assert text.strip(), path


@pytest.mark.parametrize("path", text_files(), ids=lambda path: path.name)
def test_text_rules(path: Path) -> None:
    """No em or en dashes, no emoji, no marketing words."""
    text = path.read_text(encoding="utf-8")
    for char, name in FORBIDDEN_CHARACTERS.items():
        assert char not in text, f"{name} in {path.name}"
    assert not EMOJI.search(text), f"emoji in {path.name}"
    if path.suffix != ".py" or path.parent.name != "tests":
        lower = text.lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in lower, f"{phrase!r} in {path.name}"


def test_config_flow_strings() -> None:
    """Every error and abort reason of the config flow has a text."""
    source = (PACKAGE / "config_flow.py").read_text(encoding="utf-8")
    errors = set(re.findall(r"\"base\": \"(\w+)\"", source))
    errors |= set(re.findall(r"errors\[\w+\] = \"(\w+)\"", source))
    errors |= set(_PAIR_ERRORS)
    aborts = set(re.findall(r"reason=\"(\w+)\"", source))
    # Raised by Home Assistant helpers the flow uses.
    aborts |= {"already_configured", "already_in_progress", "reauth_successful"}
    assert errors
    assert errors <= set(EN["config"]["error"]), errors - set(EN["config"]["error"])
    assert aborts <= set(EN["config"]["abort"]), aborts - set(EN["config"]["abort"])
    steps = set(re.findall(r"step_id=\"(\w+)\"", source))
    assert steps == set(EN["config"]["step"])


def test_exception_strings() -> None:
    """Every translated exception has a message, and none is unused."""
    used: set[str] = set(_OWN_MESSAGE_CODES)
    for name in ("coordinator.py", "services.py"):
        source = (PACKAGE / name).read_text(encoding="utf-8")
        used |= set(TRANSLATION_KEY.findall(source))
        used |= set(re.findall(r"_not_found\(\s*\"(\w+)\"", source))
    assert used == set(EN["exceptions"])


def test_entity_strings() -> None:
    """Every translation key of an entity has a name, and none is unused."""
    used: set[tuple[str, str]] = set()
    for platform in PLATFORMS:
        source = (PACKAGE / f"{platform}.py").read_text(encoding="utf-8")
        used |= {(platform, key) for key in TRANSLATION_KEY.findall(source)}
        used |= {
            (platform, key)
            for key in re.findall(r"_attr_translation_key = \"(\w+)\"", source)
        }
    used |= {("text", "note_line1"), ("text", "note_line2")}
    used |= {("switch", f"rotation_{mode}") for mode in KNOWN_MODES}
    used.add(("switch", "rotation_other"))
    # The light is the main feature and takes the device name.
    used.discard(("light", "panel"))
    known = {(platform, key) for platform, keys in EN["entity"].items() for key in keys}
    assert used == known
    for platform, key in known:
        assert "name" in EN["entity"][platform][key], (platform, key)


def test_select_and_showing_states() -> None:
    """Every known mode has a translated state."""
    for mode in KNOWN_MODES:
        assert mode in EN["entity"]["select"]["mode"]["state"]
        assert mode in EN["entity"]["sensor"]["showing"]["state"]
    for special in ("ring", "pairing", "hello", "off"):
        assert special in EN["entity"]["sensor"]["showing"]["state"]


def test_services_yaml_matches_translations() -> None:
    """services.yaml and en.json describe the same actions with the same words."""
    services = yaml.safe_load((PACKAGE / "services.yaml").read_text(encoding="utf-8"))
    assert set(services) == set(EN["services"]) == set(DE["services"])
    for service, spec in services.items():
        translated = EN["services"][service]
        assert spec["name"] == translated["name"]
        assert spec["description"] == translated["description"]
        assert set(spec["fields"]) == set(translated["fields"])
        assert set(spec["fields"]) == set(DE["services"][service]["fields"])
        for field, field_spec in spec["fields"].items():
            assert field_spec["name"] == translated["fields"][field]["name"]
            assert (
                field_spec["description"] == translated["fields"][field]["description"]
            )


def test_icons() -> None:
    """Icons exist only for real translation keys and both actions."""
    icons = json.loads((PACKAGE / "icons.json").read_text(encoding="utf-8"))
    for platform, keys in icons["entity"].items():
        for key in keys:
            if (platform, key) == ("light", "panel"):
                continue
            assert key in EN["entity"][platform], (platform, key)
    assert set(icons["services"]) == set(EN["services"])


def test_manifest() -> None:
    """The manifest as the project defines it."""
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "domain": "thewall",
        "name": "THE WALL",
        "codeowners": ["@LennyGodart"],
        "config_flow": True,
        "documentation": "https://github.com/LennyGodart/THE-WALL-HA",
        "integration_type": "device",
        "iot_class": "cloud_polling",
        "issue_tracker": "https://github.com/LennyGodart/THE-WALL-HA/issues",
        "requirements": [],
        "version": "0.1.1",
        "zeroconf": ["_thewall._tcp.local."],
    }
    # Home Assistant wants domain and name first, the rest sorted.
    keys = list(manifest)
    assert keys[:2] == ["domain", "name"]
    assert keys[2:] == sorted(keys[2:])


def test_hacs() -> None:
    """HACS metadata."""
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert hacs == {
        "name": "THE WALL",
        "homeassistant": "2026.3.0",
        "render_readme": True,
    }


def test_readmes_link_each_other() -> None:
    """English and German README point to each other."""
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    german = (ROOT / "README.de.md").read_text(encoding="utf-8")
    assert "(README.de.md)" in english
    assert "(README.md)" in german
