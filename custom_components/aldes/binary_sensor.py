"""Support for the Aldes binary sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, FRIENDLY_NAMES, MANUFACTURER
from .entity import AldesEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes binary sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    binary_sensors: list[AldesBinarySensorEntity] = [
        AldesBinarySensorEntity(coordinator, entry)
    ]

    async_add_entities(binary_sensors)


class AldesBinarySensorEntity(AldesEntity, BinarySensorEntity):
    """Define an Aldes binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

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
    def unique_id(self) -> str:
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.serial_number}_connectivity"

    @property
    def name(self) -> str:
        """Return a name to use for this entity."""
        return "Connectivity"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update binary sensor attributes."""
        if self.serial_number and self.coordinator.data.is_connected:
            self._attr_is_on = True
        else:
            self._attr_is_on = False
