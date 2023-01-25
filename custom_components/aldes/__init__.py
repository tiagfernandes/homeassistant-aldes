"""
Custom integration to integrate Aldes with Home Assistant.

For more details about this integration, please refer to
https://github.com/guix77/homeassistant-aldes
"""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import AldesApi
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS
from .coordinator import AldesDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
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
    return True
