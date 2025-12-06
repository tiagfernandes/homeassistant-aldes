"""
Custom integration to integrate Aldes with Home Assistant.

For more details about this integration, please refer to
https://github.com/tiagfernandes/homeassistant-aldes
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import AldesApi
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS
from .coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aldes from a config entry."""
    api = AldesApi(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        aiohttp_client.async_get_clientsession(hass),
    )
    coordinator = AldesDataUpdateCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.info("Reloading Aldes integration...")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
