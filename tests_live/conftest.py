"""Fixtures for the live test.

The live test runs Home Assistant's test harness against a real THE WALL server
instead of the fake one, with real HTTP and the real pairing code from the
server's database. It is not part of the normal run (testpaths is tests/) and
skips itself unless THEWALL_LIVE_SERVER, THEWALL_LIVE_KEY and THEWALL_LIVE_DB
are set. See tests_live/test_live_server.py.
"""

from __future__ import annotations

# isort: off
from tests import windows_compat  # noqa: F401
import pytest_homeassistant_custom_component.plugins  # noqa: F401
# isort: on

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component.plugins"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load THE WALL from custom_components."""
