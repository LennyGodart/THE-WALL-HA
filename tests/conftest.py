"""Fixtures for THE WALL tests."""

from __future__ import annotations

# isort: off
# The Windows shims come before anything that imports Home Assistant, then the
# Home Assistant test plugin, which has to patch the recorder before the rest.
from . import windows_compat  # noqa: F401
import pytest_homeassistant_custom_component.plugins  # noqa: F401
# isort: on

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
import json
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_fixture,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.thewall.const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_UID,
    DEFAULT_SERVER,
    DOMAIN,
)

from .fake_server import TOKEN, UID, FakeWall

# The Home Assistant test plugin, loaded here instead of through its entry
# point (addopts in pyproject.toml blocks that), so the shims above come first.
pytest_plugins = ["pytest_homeassistant_custom_component.plugins"]

# The "time" of tests/fixtures/state.json.
NOW_TS = 1790000000
NOW = datetime.fromtimestamp(NOW_TS, UTC)


async def tick(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Let time pass and run whatever became due, once.

    A jump over two poll intervals runs one poll, like a real clock would.
    """
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load THE WALL from custom_components."""


@pytest.fixture(autouse=True)
def frozen_clock(freezer: FrozenDateTimeFactory) -> FrozenDateTimeFactory:
    """Start every test at the time of the fixture state."""
    freezer.move_to(NOW)
    return freezer


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable the entities that are disabled by default."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ):
        yield


@pytest.fixture
def state() -> dict[str, Any]:
    """A fresh copy of the example STATE."""
    return json.loads(load_fixture("state.json"))


@pytest.fixture
def wall(aioclient_mock: AiohttpClientMocker, state: dict[str, Any]) -> FakeWall:
    """The fake server on the default address."""
    return FakeWall(aioclient_mock, state)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A paired device."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Wall",
        unique_id=UID,
        data={CONF_UID: UID, CONF_SERVER: DEFAULT_SERVER, CONF_TOKEN: TOKEN},
    )


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add the entry and wait until it is set up."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, wall: FakeWall
) -> MockConfigEntry:
    """THE WALL, set up with all platforms."""
    await setup_integration(hass, config_entry)
    return config_entry
