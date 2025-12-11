"""Support for Aldes number entities."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, FRIENDLY_NAMES, MANUFACTURER
from .entity import AldesEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import AldesDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)

# Constants
DEBOUNCE_SECONDS = 2.0
REFRESH_DELAY_SECONDS = 10.0
DEFAULT_PRICE_CREUSE = 0.150
DEFAULT_PRICE_PLEINE = 0.200


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes number entities from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            AldesKwhCreuseNumber(coordinator, entry),
            AldesKwhPleineNumber(coordinator, entry),
        ]
    )


class AldesKwhPriceNumber(AldesEntity, NumberEntity):
    """Base class for kWh price number entities."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 0.999
    _attr_native_step = 0.001
    _attr_native_unit_of_measurement = "€/kWh"
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:currency-eur"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: AldesDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, config_entry)
        self._pending_update_task: asyncio.Task | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    def _get_settings_value(self, attribute: str, default: float) -> float:
        """Get value from coordinator settings with fallback."""
        if (
            self.coordinator.data
            and self.coordinator.data.indicator
            and self.coordinator.data.indicator.settings
        ):
            value = getattr(self.coordinator.data.indicator.settings, attribute, None)
            if value is not None:
                return value
        return default

    async def async_set_native_value(self, value: float) -> None:
        """Update the price with debounce."""
        if self._pending_update_task and not self._pending_update_task.done():
            self._pending_update_task.cancel()

        self._pending_update_task = asyncio.create_task(self._debounced_update(value))

    async def _debounced_update(self, value: float) -> None:
        """Execute the update after debounce delay."""
        try:
            await asyncio.sleep(DEBOUNCE_SECONDS)
            await self._send_price_update(value)
        except asyncio.CancelledError:
            _LOGGER.debug("Price update cancelled due to new value")
            raise

    async def _send_price_update(self, value: float) -> None:
        """Send price update to API - to be implemented by subclasses."""
        raise NotImplementedError

    async def _set_kwh_prices(self, kwh_pleine: float, kwh_creuse: float) -> None:
        """Set kWh prices via API."""
        if not self.coordinator.data or not self.coordinator.data.modem:
            _LOGGER.error("Modem not available")
            return

        await self.coordinator.api.set_kwh_prices(
            self.coordinator.data.modem, kwh_pleine, kwh_creuse
        )
        await asyncio.sleep(REFRESH_DELAY_SECONDS)
        await self.coordinator.async_request_refresh()


class AldesKwhCreuseNumber(AldesKwhPriceNumber):
    """Number entity for off-peak hour electricity price."""

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_kwh_creuse"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Tarif heures creuses"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        if not (
            self.coordinator.data
            and self.coordinator.data.indicator
            and self.coordinator.data.indicator.settings
        ):
            return None
        return self.coordinator.data.indicator.settings.kwh_creuse

    async def _send_price_update(self, value: float) -> None:
        """Send creuse price update to API."""
        kwh_pleine = self._get_settings_value("kwh_pleine", DEFAULT_PRICE_PLEINE)
        await self._set_kwh_prices(kwh_pleine, value)


class AldesKwhPleineNumber(AldesKwhPriceNumber):
    """Number entity for peak hour electricity price."""

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_kwh_pleine"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Tarif heures pleines"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        if not (
            self.coordinator.data
            and self.coordinator.data.indicator
            and self.coordinator.data.indicator.settings
        ):
            return None
        return self.coordinator.data.indicator.settings.kwh_pleine

    async def _send_price_update(self, value: float) -> None:
        """Send pleine price update to API."""
        kwh_creuse = self._get_settings_value("kwh_creuse", DEFAULT_PRICE_CREUSE)
        await self._set_kwh_prices(value, kwh_creuse)
