"""
Custom integration to integrate Aldes with Home Assistant.

For more details about this integration, please refer to
https://github.com/tiagfernandes/homeassistant-aldes
"""

import logging
from datetime import UTC, datetime
from datetime import date as dt_date
from datetime import time as dt_time
from functools import partial
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import AldesApi
from .const import (
    CONF_PASSWORD,
    CONF_PERFORMANCE_LOGS,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import AldesDataUpdateCoordinator
from .entity import DataApiEntity

_LOGGER = logging.getLogger(__name__)


API_DATE_FORMAT_LENGTH = 15


def coerce_time(value: str | dt_time | None) -> dt_time:
    """Convert string to time object."""
    if value is None:
        return dt_time(0, 0, 0)
    if isinstance(value, dt_time):
        return value
    if isinstance(value, str):
        try:
            return dt_time.fromisoformat(value)
        except ValueError:
            return dt_time(0, 0, 0)
    return dt_time(0, 0, 0)


def _update_log_level(entry: ConfigEntry) -> None:
    """Update log level based on configuration."""
    performance_logs = entry.options.get(CONF_PERFORMANCE_LOGS, False)
    api_logger = logging.getLogger("custom_components.aldes.api")
    if performance_logs:
        api_logger.setLevel(logging.DEBUG)
        _LOGGER.info("Performance logs enabled for Aldes API")
    else:
        # Restore default level (usually NOTSET which inherits from parent)
        api_logger.setLevel(logging.NOTSET)
        _LOGGER.debug("Performance logs disabled for Aldes API")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aldes from a config entry."""
    _update_log_level(entry)

    token = entry.options.get("token", "")
    api = AldesApi(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        aiohttp_client.async_get_clientsession(hass),
        token,
    )

    if not token or not await api.check_token_validity():
        _LOGGER.info("Token missing or invalid, authenticating...")
        await api.authenticate()
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, "token": api.token},
        )

    coordinator = AldesDataUpdateCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_request_refresh()

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register web resources for Lovelace card
    await _register_lovelace_resources(hass)

    # Register services
    await _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator:
            await coordinator.api.async_close()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.info("Reloading Aldes integration...")
    _update_log_level(entry)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _register_lovelace_resources(hass: HomeAssistant) -> None:
    """Register Lovelace card resources."""
    from aiohttp import web
    from homeassistant.components.http import HomeAssistantView

    class AldesCardView(HomeAssistantView):
        """View to serve the Aldes planning card."""

        requires_auth = False
        url = "/aldes_planning_card.js"
        name = "aldes:planning_card"

        async def get(self, _request: web.Request) -> web.Response:
            """Serve the card JavaScript file."""
            card_path = Path(__file__).parent / "lovelace" / "aldes-planning-card.js"
            try:
                # Use executor to avoid blocking the event loop
                content = await hass.async_add_executor_job(
                    card_path.read_text, "utf-8"
                )
                return web.Response(
                    text=content,
                    content_type="application/javascript",
                    headers={"Cache-Control": "no-cache"},
                )
            except FileNotFoundError:
                _LOGGER.exception("Card file not found: %s", card_path)
                return web.Response(text="// Card not found", status=404)

    hass.http.register_view(AldesCardView())
    _LOGGER.info("Aldes planning card view registered at /aldes_planning_card.js")


def _get_primary_device(
    coordinator: AldesDataUpdateCoordinator | None,
) -> DataApiEntity | None:
    """Return the first available device from a coordinator."""
    if coordinator and coordinator.data:
        # Prefer a connected device when multiple devices are available
        for device in coordinator.data.values():
            try:
                if getattr(device, "is_connected", False):
                    return device
            except AttributeError:
                # Ignore missing attribute and continue
                continue
        # Fallback to the first device if none are connected
        for device in coordinator.data.values():
            return device
    return None


def _get_identifier_from_device_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Get Aldes identifier (serial/modem) from a device_id."""
    registry = dr.async_get(hass)
    device_entry = registry.async_get(device_id)
    if not device_entry:
        return None
    target = device_entry
    if device_entry.via_device_id:
        parent = registry.async_get(device_entry.via_device_id)
        if parent:
            target = parent
    for domain, identifier in target.identifiers:
        if domain == DOMAIN:
            return identifier
    return None


def _find_device_in_coordinator(
    coordinator: AldesDataUpdateCoordinator | None, identifier: str | None
) -> DataApiEntity | None:
    """Find device in coordinator by identifier."""
    if not coordinator or not coordinator.data or not identifier:
        return None
    for device in coordinator.data.values():
        if identifier in {device.serial_number, device.modem}:
            return device
    return None


def _get_coordinator_and_device(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[AldesDataUpdateCoordinator | None, DataApiEntity | None]:
    """Get coordinator and device from service call data."""
    device_id = call.data.get("device_id")
    entity_id = call.data.get("entity_id")

    if entity_id:
        return _get_by_entity_id(hass, entity_id)
    if device_id:
        return _get_by_device_id(hass, device_id)
    return _get_default_coordinator(hass)


def _get_by_entity_id(
    hass: HomeAssistant, entity_id: str
) -> tuple[AldesDataUpdateCoordinator | None, DataApiEntity | None]:
    """Resolve coordinator and device from an entity_id."""
    registry = er.async_get(hass)
    entity_entry = registry.async_get(entity_id)
    if not entity_entry:
        _LOGGER.error("Entity %s not found", entity_id)
        return None, None
    coordinator = hass.data[DOMAIN].get(entity_entry.config_entry_id)
    if not coordinator:
        _LOGGER.error("Coordinator not found for entity %s", entity_id)
        return None, None
    device = None
    if entity_entry.device_id:
        identifier = _get_identifier_from_device_id(hass, entity_entry.device_id)
        device = _find_device_in_coordinator(coordinator, identifier)
    if not device:
        device = _get_primary_device(coordinator)
    return coordinator, device


def _get_by_device_id(
    hass: HomeAssistant, device_id: str
) -> tuple[AldesDataUpdateCoordinator | None, DataApiEntity | None]:
    """Resolve coordinator and device from a device_id."""
    identifier = _get_identifier_from_device_id(hass, device_id)
    if identifier:
        for coordinator in hass.data[DOMAIN].values():
            device = _find_device_in_coordinator(coordinator, identifier)
            if device:
                return coordinator, device
    _LOGGER.error("No Aldes device found for device_id %s", device_id)
    return None, None


def _get_default_coordinator(
    hass: HomeAssistant,
) -> tuple[AldesDataUpdateCoordinator | None, DataApiEntity | None]:
    """Fallback to the first coordinator/device if available."""
    coordinators = list(hass.data[DOMAIN].values())
    if not coordinators:
        _LOGGER.error("No Aldes device found")
        return None, None
    coordinator = coordinators[0]
    return coordinator, _get_primary_device(coordinator)


def _parse_service_datetime(
    date_input: str | dt_date, time_input: dt_time, label: str
) -> datetime | None:
    """Parse service date/time input into aware UTC datetime."""
    if isinstance(date_input, datetime.date):
        parsed = datetime.combine(date_input, time_input)
    elif isinstance(date_input, str):
        if len(date_input) == API_DATE_FORMAT_LENGTH and date_input.endswith("Z"):
            parsed = datetime.strptime(
                date_input.replace("Z", "+0000"), "%Y%m%d%H%M%S%z"
            )
        else:
            try:
                parsed_date = datetime.fromisoformat(date_input.replace("Z", "+00:00"))
                parsed = datetime.combine(parsed_date.date(), time_input)
            except ValueError:
                _LOGGER.exception("Invalid %s format: %s", label, date_input)
                return None
    else:
        _LOGGER.error("Unexpected %s type: %s", label, type(date_input))
        return None

    if parsed.tzinfo is None:
        parsed = dt_util.as_local(parsed)
    return parsed.astimezone(UTC)


async def _handle_set_week_planning(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set week planning (mode A/B) for an Aldes device."""
    planning: str = call.data["planning"]
    mode: str = call.data.get("mode", "A")

    coordinator, device = _get_coordinator_and_device(hass, call)
    if not coordinator or not device:
        return

    if not device.modem:
        _LOGGER.error("Modem not available")
        return

    await coordinator.api.change_week_planning(device.modem, planning, mode)
    await coordinator.async_request_refresh()


async def _handle_set_holidays(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set holidays mode for an Aldes device."""
    start_date_input = call.data["start_date"]
    start_time_input = call.data.get("start_time", dt_time(0, 0, 0))
    end_date_input = call.data["end_date"]
    end_time_input = call.data.get("end_time", dt_time(0, 0, 0))

    start_datetime_utc = _parse_service_datetime(
        start_date_input, start_time_input, "start_date"
    )
    end_datetime_utc = _parse_service_datetime(
        end_date_input, end_time_input, "end_date"
    )
    if not start_datetime_utc or not end_datetime_utc:
        return

    start_date = start_datetime_utc.strftime("%Y%m%d%H%M%SZ")
    end_date = end_datetime_utc.strftime("%Y%m%d%H%M%SZ")

    coordinator, device = _get_coordinator_and_device(hass, call)
    if not coordinator or not device:
        return

    if not device.modem:
        _LOGGER.error("Modem not available")
        return

    await coordinator.api.set_holidays_mode(device.modem, start_date, end_date)
    await coordinator.async_request_refresh()


async def _handle_cancel_holidays(hass: HomeAssistant, call: ServiceCall) -> None:
    """Cancel holidays mode for an Aldes device."""
    coordinator, device = _get_coordinator_and_device(hass, call)
    if not coordinator or not device:
        return

    if not device.modem:
        _LOGGER.error("Modem not available")
        return

    await coordinator.api.cancel_holidays_mode(device.modem)
    await coordinator.async_request_refresh()


async def _handle_set_frost_protection(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set frost protection mode for an Aldes device."""
    start_date_input = call.data["start_date"]
    start_time_input = call.data.get("start_time", dt_time(0, 0, 0))

    start_datetime_utc = _parse_service_datetime(
        start_date_input, start_time_input, "start_date"
    )
    if not start_datetime_utc:
        return

    start_date = start_datetime_utc.strftime("%Y%m%d%H%M%SZ")

    coordinator, device = _get_coordinator_and_device(hass, call)
    if not coordinator or not device:
        return

    if not device.modem:
        _LOGGER.error("Modem not available")
        return

    await coordinator.api.set_frost_protection_mode(device.modem, start_date)
    await coordinator.async_request_refresh()


async def _handle_update_credentials(hass: HomeAssistant, call: ServiceCall) -> None:
    """Update login and password."""
    entry_id = call.data.get("entry_id")
    new_username = call.data.get("username")
    new_password = call.data.get("password")

    if not entry_id or not new_username or not new_password:
        _LOGGER.error("entry_id, username, and password are required")
        return

    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry:
        _LOGGER.error("Entry %s not found", entry_id)
        return

    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_USERNAME: new_username, CONF_PASSWORD: new_password},
        options={**entry.options, "token": ""},
    )
    await hass.config_entries.async_reload(entry_id)


async def _register_services(hass: HomeAssistant) -> None:
    """Register Aldes services."""
    hass.services.async_register(
        DOMAIN,
        "set_week_planning",
        partial(_handle_set_week_planning, hass),
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
                vol.Required("planning"): str,
                vol.Optional("mode", default="A"): str,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "set_holidays",
        partial(_handle_set_holidays, hass),
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

    hass.services.async_register(
        DOMAIN,
        "cancel_holidays",
        partial(_handle_cancel_holidays, hass),
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "set_frost_protection",
        partial(_handle_set_frost_protection, hass),
        schema=vol.Schema(
            {
                vol.Optional("device_id"): str,
                vol.Optional("entity_id"): str,
                vol.Required("start_date"): vol.Any(str, vol.Coerce(datetime.date)),
                vol.Optional("start_time", default="00:00:00"): coerce_time,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "update_credentials",
        partial(_handle_update_credentials, hass),
        schema=vol.Schema(
            {
                vol.Required("entry_id"): str,
                vol.Required("username"): str,
                vol.Required("password"): str,
            }
        ),
    )
