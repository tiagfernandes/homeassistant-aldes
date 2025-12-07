"""
Custom integration to integrate Aldes with Home Assistant.

For more details about this integration, please refer to
https://github.com/tiagfernandes/homeassistant-aldes
"""

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import aiohttp_client
import voluptuous as vol

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

    # Register web resources for Lovelace card
    _register_lovelace_resources(hass)

    # Register services
    await _register_services(hass)

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


def _register_lovelace_resources(hass: HomeAssistant) -> None:
    """Register Lovelace card resources."""
    from aiohttp import web
    from homeassistant.components.http import HomeAssistantView

    class AldesCardView(HomeAssistantView):
        """View to serve the Aldes planning card."""

        requires_auth = False
        url = "/aldes_planning_card.js"
        name = "aldes:planning_card"

        async def get(self, request):
            """Serve the card JavaScript file."""
            _LOGGER.info("Aldes planning card requested")
            card_path = Path(__file__).parent / "lovelace" / "aldes-planning-card.js"
            try:
                # Use executor to avoid blocking the event loop
                content = await hass.async_add_executor_job(
                    card_path.read_text, "utf-8"
                )
                _LOGGER.debug(
                    "Serving card from: %s (%d bytes)", card_path, len(content)
                )
                return web.Response(
                    text=content,
                    content_type="application/javascript",
                    headers={"Cache-Control": "no-cache"},
                )
            except FileNotFoundError:
                _LOGGER.error("Card file not found: %s", card_path)
                return web.Response(text="// Card not found", status=404)

    hass.http.register_view(AldesCardView())
    _LOGGER.info("Aldes planning card view registered at /aldes_planning_card.js")


async def _register_services(hass: HomeAssistant) -> None:
    """Register Aldes services."""

    async def async_set_week_planning(call: ServiceCall) -> None:
        """Set week planning (mode A/B) for an Aldes device."""
        entity_id: str = call.data["entity_id"]
        planning: str = call.data["planning"]
        mode: str = call.data.get("mode", "A")

        registry = er.async_get(hass)
        entity_entry = registry.async_get(entity_id)
        if not entity_entry:
            _LOGGER.error("Entity %s not found for set_week_planning", entity_id)
            return

        entry_id = entity_entry.config_entry_id
        coordinator = hass.data[DOMAIN].get(entry_id)
        if not coordinator:
            _LOGGER.error(
                "Coordinator not found for entry %s while setting week planning",
                entry_id,
            )
            return

        modem = coordinator.data.modem if coordinator.data else None
        if not modem:
            _LOGGER.error("Modem not available for entity %s", entity_id)
            return

        await coordinator.api.change_week_planning(modem, planning, mode)
        # Optionally refresh after update
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "set_week_planning",
        async_set_week_planning,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): str,
                vol.Required("planning"): str,
                vol.Optional("mode", default="A"): str,
            }
        ),
    )
