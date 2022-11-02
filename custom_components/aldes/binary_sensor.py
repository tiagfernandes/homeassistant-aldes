"""Support for the Aldes binary sensors."""
from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER, FRIENDLY_NAMES
from .entity import AldesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes binary sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    binary_sensors: list[AldesBinarySensorEntity] = []

    for product in coordinator.data:
        binary_sensors.append(
            AldesBinarySensorEntity(
                coordinator,
                entry,
                product["serial_number"],
                product["reference"],
                product["modem"],
            )
        )

    async_add_entities(binary_sensors)


class AldesBinarySensorEntity(AldesEntity, BinarySensorEntity):
    """Define an Aldes binary sensor."""

    _attr_device_class = "connectivity"

    @property
    def device_info(self):
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.product_serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.product_serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_connectivity"

    @property
    def name(self):
        """Return a name to use for this entity."""
        return f"{MANUFACTURER} {self.product_serial_number} connectivity"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update binary sensor attributes."""
        for product in self.coordinator.data:
            if product["serial_number"] == self.product_serial_number:
                if product["isConnected"]:
                    self._attr_is_on = True
                else:
                    self._attr_is_on = False
