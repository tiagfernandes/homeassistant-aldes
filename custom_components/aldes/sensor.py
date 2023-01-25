"""Support for the Aldes sensors."""
from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER
from .entity import AldesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[AldesSensorEntity] = []

    for product in coordinator.data:
        for thermostat in product["indicator"]["thermostats"]:
            sensors.append(
                AldesSensorEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    product["modem"],
                    thermostat["ThermostatId"],
                )
            )

    async_add_entities(sensors)


class AldesSensorEntity(AldesEntity, SensorEntity):
    """Define an Aldes sensor."""

    def __init__(
        self,
        coordinator,
        config_entry,
        product_serial_number,
        reference,
        modem,
        thermostat_id,
    ):
        super().__init__(
            coordinator, config_entry, product_serial_number, reference, modem
        )
        self.thermostat_id = thermostat_id
        self._attr_device_class = "temperature"
        self._attr_native_unit_of_measurement = TEMP_CELSIUS

    @property
    def device_info(self):
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.thermostat_id)},
            manufacturer=MANUFACTURER,
            name=f"Thermostat {self.thermostat_id}",
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.thermostat_id}_temperature"

    @property
    def name(self):
        """Return a name to use for this entity."""
        for product in self.coordinator.data:
            if product["serial_number"] == self.product_serial_number:
                for thermostat in product["indicator"]["thermostats"]:
                    if thermostat["ThermostatId"] == self.thermostat_id:
                        return f"{thermostat['Name']} temperature"
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update binary sensor attributes."""
        for product in self.coordinator.data:
            if product["isConnected"]:
                if product["serial_number"] == self.product_serial_number:
                    for thermostat in product["indicator"]["thermostats"]:
                        if thermostat["ThermostatId"] == self.thermostat_id:
                            self._attr_native_value = round(
                                thermostat["CurrentTemperature"], 1
                            )
            else:
                self._attr_native_value = None
