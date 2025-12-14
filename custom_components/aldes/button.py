"""Support for Aldes buttons."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, FRIENDLY_NAMES, MANUFACTURER
from .entity import AldesEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes buttons from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    buttons: list[AldesResetFilterButton] = [AldesResetFilterButton(coordinator, entry)]

    async_add_entities(buttons)


class AldesResetFilterButton(AldesEntity, ButtonEntity):
    """Define an Aldes reset filter button."""

    _attr_icon = "mdi:air-filter"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_reset_filter"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Réinitialiser le filtre"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.reset_filter(self.modem)
        # Request refresh after reset
        await self.coordinator.async_request_refresh()
