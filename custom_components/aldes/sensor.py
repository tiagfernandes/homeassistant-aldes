"""Support for the Aldes sensors."""
from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER, FRIENDLY_NAMES
from .entity import AldesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for product in coordinator.data:
        # Collect thermostat sensors
        for thermostat in product["indicator"]["thermostats"]:
            sensors.append(
                AldesThermostatSensorEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    product["modem"],
                    thermostat["ThermostatId"],
                    thermostat["Name"],
                )
            )

        # Collect Main Room Temperature sensor
        sensors.append(AldesMainRoomTemperatureEntity(
            coordinator,
            entry,
            product["serial_number"],
            product["reference"],
            product["modem"]
        ))

        # Collect water tank entities if AquaAir reference
        if product['reference'] == "TONE_AQUA_AIR":
            sensors.append(
                AldesWaterTankEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    product["modem"]
                )
            )

    async_add_entities(sensors)


class AldesThermostatSensorEntity(AldesEntity, SensorEntity):
    """Define an Aldes thermostat sensor."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem, thermostat_id, thermostat_name):
        super().__init__(
            coordinator, config_entry, product_serial_number, reference, modem
        )
        self.thermostat_id = thermostat_id
        self.thermostat_name = thermostat_name
        self._attr_device_class = "temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def device_info(self):
        """Return the device info."""
        name = f"Thermostat {self.thermostat_name}" if self.thermostat_name else f"Thermostat {self.thermostat_id}"

        return DeviceInfo(
            identifiers={(DOMAIN, self.thermostat_id)},
            manufacturer=MANUFACTURER,
            name=name,
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.thermostat_id}_temperature"

    @property
    def name(self):
        """Return a name to use for this entity."""
        return self.thermostat_name or f"Thermostat {self.thermostat_id} Temperature"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""
        # Extract relevant data once for efficiency
        thermostat = next(
            (
                thermostat
                for product in self.coordinator.data
                if product["serial_number"] == self.product_serial_number
                for thermostat in product["indicator"]["thermostats"]
                if thermostat["ThermostatId"] == self.thermostat_id
            ),
            None,
        )
        if thermostat:
            self._attr_native_value = thermostat["CurrentTemperature"]


class AldesWaterTankEntity(AldesEntity, SensorEntity):
    """Define an Aldes Water Tank Quantity sensor."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(
            coordinator, config_entry, product_serial_number, reference, modem
        )
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._state = None

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
        return f"{DOMAIN}_{self.product_serial_number}_water_tank_quantity"

    @property
    def name(self):
        """Return a name to use for this entity."""
        return "Water Tank Quantity"

    @property
    def icon(self) -> str:
        """Return the appropriate icon based on the state."""
        if self._state is None or not isinstance(self._state, (int, float)):
            return "mdi:water-boiler"  # Default icon
        if self._state <= 25:
            return "mdi:gauge-empty"
        elif self._state <= 50:
            return "mdi:gauge-low"
        elif self._state <= 75:
            return "mdi:gauge"
        else:
            return "mdi:gauge-full"

    @property
    def native_value(self):
        """Returns the current sensor value."""
        return self._state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update the water tank attributes."""
        product = next(
            (
                product
                for product in self.coordinator.data
                if product["serial_number"] == self.product_serial_number and product["isConnected"]
            ),
            None,
        )
        if product:
            self._state = product["indicator"].get("qte_eau_chaude", None)
        else:
            self._state = None


class AldesMainRoomTemperatureEntity(AldesEntity, SensorEntity):
    """Define an Aldes Main Room Temperature sensor."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(
            coordinator, config_entry, product_serial_number, reference, modem
        )
        self._attr_device_class = "temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._state = None

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
        return f"{DOMAIN}_{self.product_serial_number}_main_room_temperature"

    @property
    def name(self):
        """Return a name to use for this entity."""
        return "Main room temperature"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""
        for product in self.coordinator.data:
            if product["isConnected"]:
                if product["serial_number"] == self.product_serial_number:
                    self._state = product["indicator"]["tmp_principal"]
            else:
                self._state = None

    @property
    def native_value(self):
        """Return the current sensor value."""
        return self._state
