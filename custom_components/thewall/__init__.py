"""THE WALL: a 128x64 LED panel, controlled through its server."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import TheWallClient, TheWallError
from .const import CONF_SERVER, CONF_TOKEN, DOMAIN, LOGGER
from .coordinator import TheWallConfigEntry, TheWallCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
    Platform.UPDATE,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TheWallConfigEntry) -> bool:
    """Set up one device."""
    client = TheWallClient(
        async_get_clientsession(hass), entry.data[CONF_SERVER], entry.data[CONF_TOKEN]
    )
    coordinator = TheWallCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TheWallConfigEntry) -> bool:
    """Unload one device."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: TheWallConfigEntry) -> None:
    """Revoke the token on the server. Errors do not stop the removal."""
    server = entry.data.get(CONF_SERVER)
    token = entry.data.get(CONF_TOKEN)
    if not server or not token:
        return
    client = TheWallClient(async_get_clientsession(hass), server, token)
    try:
        await client.unlink()
    except TheWallError as err:
        LOGGER.debug("Could not unlink %s from the server: %s", entry.title, err)
