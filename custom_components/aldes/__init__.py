"""
Custom integration to integrate Aldes with Home Assistant.

For more details about this integration, please refer to
https://github.com/tiagfernandes/homeassistant-aldes
"""

import logging
from datetime import UTC, datetime
from datetime import time as dt_time
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import entity_registry as er

from .api import AldesApi
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS
from .coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def coerce_time(value: str | dt_time | None) -> dt_time:
    """Convert string to time object."""
    if value is None:
        return dt_time(0, 0, 0)
    if isinstance(value, dt_time):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%H:%M:%S").time()
        except ValueError:
            return dt_time(0, 0, 0)
    return dt_time(0, 0, 0)


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

    def _get_coordinator_from_call(call: ServiceCall):
        """Get coordinator from service call data."""
        device_id = call.data.get("device_id")
        entity_id = call.data.get("entity_id")

        # If device_id is provided, use it
        if device_id:
            registry = er.async_get(hass)
            # Find any entity for this device
            entities = er.async_entries_for_device(registry, device_id)
            for entity in entities:
                if entity.platform == DOMAIN:
                    entry_id = entity.config_entry_id
                    coordinator = hass.data[DOMAIN].get(entry_id)
                    if coordinator:
                        return coordinator
            _LOGGER.error("No Aldes entities found for device %s", device_id)
            return None

        # If entity_id is provided, use it
        if entity_id:
            registry = er.async_get(hass)
            entity_entry = registry.async_get(entity_id)
            if not entity_entry:
                _LOGGER.error("Entity %s not found", entity_id)
                return None
            entry_id = entity_entry.config_entry_id
            coordinator = hass.data[DOMAIN].get(entry_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for entity %s", entity_id)
            return coordinator

        # If neither is provided, use the first available coordinator
        coordinators = list(hass.data[DOMAIN].values())
        if coordinators:
            _LOGGER.info("Using first available Aldes device")
            return coordinators[0]

        _LOGGER.error("No Aldes device found")
        return None

    async def async_set_week_planning(call: ServiceCall) -> None:
        """Set week planning (mode A/B) for an Aldes device."""
        planning: str = call.data["planning"]
        mode: str = call.data.get("mode", "A")

        coordinator = _get_coordinator_from_call(call)
        if not coordinator:
            return

        modem = coordinator.data.modem if coordinator.data else None
        if not modem:
            _LOGGER.error("Modem not available")
            return

        await coordinator.api.change_week_planning(modem, planning, mode)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "set_week_planning",
        async_set_week_planning,
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
                vol.Required("planning"): str,
                vol.Optional("mode", default="A"): str,
            }
        ),
    )

    async def async_set_holidays(call: ServiceCall) -> None:
        """Set holidays mode for an Aldes device."""
        from datetime import date as dt_date
        from datetime import datetime

        start_date_input = call.data["start_date"]
        start_time_input = call.data.get("start_time", dt_time(0, 0, 0))
        end_date_input = call.data["end_date"]
        end_time_input = call.data.get("end_time", dt_time(0, 0, 0))

        # Times already converted to time objects by schema

        # Combine date and time into datetime objects
        if isinstance(start_date_input, dt_date):
            # Date object from selector
            start_datetime = datetime.combine(start_date_input, start_time_input)
        elif isinstance(start_date_input, str):
            # Try different string formats
            api_date_format_length = 15
            if len(
                start_date_input
            ) == api_date_format_length and start_date_input.endswith("Z"):
                # Format: 20251210000000Z
                start_datetime = datetime.strptime(
                    start_date_input, "%Y%m%d%H%M%SZ"
                ).replace(tzinfo=UTC)
            else:
                # Format: YYYY-MM-DD or other ISO formats
                try:
                    start_date_parsed = datetime.fromisoformat(
                        start_date_input.replace("Z", "+00:00")
                    )
                    start_datetime = datetime.combine(
                        start_date_parsed.date(), start_time_input
                    )
                except ValueError:
                    _LOGGER.exception("Invalid start_date format: %s", start_date_input)
                    return
        else:
            _LOGGER.error("Unexpected start_date type: %s", type(start_date_input))
            return

        if isinstance(end_date_input, dt_date):
            # Date object from selector
            end_datetime = datetime.combine(end_date_input, end_time_input)
        elif isinstance(end_date_input, str):
            # Try different string formats
            api_date_format_length = 15
            if len(
                end_date_input
            ) == api_date_format_length and end_date_input.endswith("Z"):
                # Format: 20260105000000Z
                end_datetime = datetime.strptime(
                    end_date_input, "%Y%m%d%H%M%SZ"
                ).replace(tzinfo=UTC)
            else:
                # Format: YYYY-MM-DD or other ISO formats
                try:
                    end_date_parsed = datetime.fromisoformat(
                        end_date_input.replace("Z", "+00:00")
                    )
                    end_datetime = datetime.combine(
                        end_date_parsed.date(), end_time_input
                    )
                except ValueError:
                    _LOGGER.exception("Invalid end_date format: %s", end_date_input)
                    return
        else:
            _LOGGER.error("Unexpected end_date type: %s", type(end_date_input))
            return

        # Convert to UTC (API expects UTC timezone)
        # Assume local timezone if not specified
        from homeassistant.util import dt as dt_util

        if start_datetime.tzinfo is None:
            start_datetime = dt_util.as_local(start_datetime)
        start_datetime_utc = start_datetime.astimezone(UTC)

        if end_datetime.tzinfo is None:
            end_datetime = dt_util.as_local(end_datetime)
        end_datetime_utc = end_datetime.astimezone(UTC)

        # Convert to API format yyyyMMddHHmmssZ
        start_date = start_datetime_utc.strftime("%Y%m%d%H%M%SZ")
        end_date = end_datetime_utc.strftime("%Y%m%d%H%M%SZ")

        coordinator = _get_coordinator_from_call(call)
        if not coordinator:
            return

        modem = coordinator.data.modem if coordinator.data else None
        if not modem:
            _LOGGER.error("Modem not available")
            return

        await coordinator.api.set_holidays_mode(modem, start_date, end_date)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "set_holidays",
        async_set_holidays,
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
                vol.Required("start_date"): vol.Any(str, vol.Coerce(datetime.date)),
                vol.Optional("start_time", default="00:00:00"): coerce_time,
                vol.Required("end_date"): vol.Any(str, vol.Coerce(datetime.date)),
                vol.Optional("end_time", default="00:00:00"): coerce_time,
            }
        ),
    )

    async def async_cancel_holidays(call: ServiceCall) -> None:
        """Cancel holidays mode for an Aldes device."""
        coordinator = _get_coordinator_from_call(call)
        if not coordinator:
            return

        modem = coordinator.data.modem if coordinator.data else None
        if not modem:
            _LOGGER.error("Modem not available")
            return

        await coordinator.api.cancel_holidays_mode(modem)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "cancel_holidays",
        async_cancel_holidays,
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
            }
        ),
    )

    async def async_set_frost_protection(call: ServiceCall) -> None:
        """Set frost protection mode for an Aldes device."""
        from datetime import date as dt_date
        from datetime import datetime

        start_date_input = call.data["start_date"]
        start_time_input = call.data.get("start_time", dt_time(0, 0, 0))

        # start_time_input is already converted to time object by the schema

        # Combine date and time into datetime object
        if isinstance(start_date_input, dt_date):
            # Date object from selector
            start_datetime = datetime.combine(start_date_input, start_time_input)
        elif isinstance(start_date_input, str):
            # Try different string formats
            if len(start_date_input) == 15 and start_date_input.endswith("Z"):
                # Format: 20251210000000Z
                start_datetime = datetime.strptime(start_date_input, "%Y%m%d%H%M%SZ")
            else:
                # Format: YYYY-MM-DD or other ISO formats
                try:
                    start_date_parsed = datetime.fromisoformat(
                        start_date_input.replace("Z", "+00:00")
                    )
                    start_datetime = datetime.combine(
                        start_date_parsed.date(), start_time_input
                    )
                except ValueError:
                    _LOGGER.error("Invalid start_date format: %s", start_date_input)
                    return
        else:
            _LOGGER.error("Unexpected start_date type: %s", type(start_date_input))
            return

        # Convert to UTC (API expects UTC timezone)
        # Assume local timezone if not specified
        from homeassistant.util import dt as dt_util

        if start_datetime.tzinfo is None:
            start_datetime = dt_util.as_local(start_datetime)
        start_datetime_utc = start_datetime.astimezone(UTC)

        # Convert to API format yyyyMMddHHmmssZ
        start_date = start_datetime_utc.strftime("%Y%m%d%H%M%SZ")

        coordinator = _get_coordinator_from_call(call)
        if not coordinator:
            return

        modem = coordinator.data.modem if coordinator.data else None
        if not modem:
            _LOGGER.error("Modem not available")
            return

        await coordinator.api.set_frost_protection_mode(modem, start_date)
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "set_frost_protection",
        async_set_frost_protection,
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
                vol.Required("start_date"): vol.Any(str, vol.Coerce(datetime.date)),
                vol.Optional("start_time", default="00:00:00"): coerce_time,
            }
        ),
    )
