"""Support for the Aldes sensors."""
from __future__ import annotations
from typing import Any, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.components.sensor import SensorEntity
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
        # Check connection status and ensure required keys exist
        if not product.get("isConnected") or "indicator" not in product:
            continue

        # Collect thermostat sensors
        for thermostat in product["indicator"].get("thermostats", []):
            sensors.append(
                AldesThermostatSensorEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    product["modem"],
                    thermostat.get("ThermostatId"),
                    thermostat.get("Name"),
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

        # Collect water entities if AquaAir reference
        if product["reference"] == "TONE_AQUA_AIR":
            sensors.append(
                AldesWaterEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    product["modem"]
                )
            )

    async_add_entities(sensors)


class BaseAldesSensorEntity(AldesEntity, SensorEntity):
    """Base class for Aldes sensors with common attributes and methods."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(coordinator, config_entry, product_serial_number, reference, modem)
        self._state: Optional[Any] = None

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        return self._state

    @callback
    def _update_state(self, value: Any) -> None:
        """Update the internal state and notify Home Assistant."""
        self._state = value
        self.async_write_ha_state()


class AldesThermostatSensorEntity(BaseAldesSensorEntity):
    """Define an Aldes thermostat sensor."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem, thermostat_id, thermostat_name):
        super().__init__(coordinator, config_entry, product_serial_number, reference, modem)
        self.thermostat_id = thermostat_id
        self.thermostat_name = thermostat_name
        self._attr_device_class = "temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        name = f"Thermostat {self.thermostat_name}" if self.thermostat_name else f"Thermostat {self.thermostat_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, self.thermostat_id)},
            manufacturer=MANUFACTURER,
            name=name,
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_{self.thermostat_id}_temperature"

    @property
    def name(self) -> str:
        """Return a name for this entity."""
        return self.thermostat_name or f"Thermostat {self.thermostat_id} Temperature"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        thermostat = next(
            (
                t
                for product in self.coordinator.data
                if product["serial_number"] == self.product_serial_number
                for t in product["indicator"].get("thermostats", [])
                if t["ThermostatId"] == self.thermostat_id
            ),
            None,
        )
        self._update_state(thermostat.get("CurrentTemperature") if thermostat else None)
        super()._handle_coordinator_update()


class AldesWaterEntity(BaseAldesSensorEntity):
    """Define an Aldes Water Quantity sensor."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(coordinator, config_entry, product_serial_number, reference, modem)
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.product_serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.product_serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_water_quantity"

    @property
    def name(self) -> str:
        """Return a name for this entity."""
        return "Water Quantity"

    @property
    def icon(self) -> str:
        """Return an icon based on water level."""
        if self._state is None or not isinstance(self._state, (int, float)):
            return "mdi:water-boiler"
        if self._state <= 25:
            return "mdi:gauge-empty"
        elif self._state <= 50:
            return "mdi:gauge-low"
        elif self._state <= 75:
            return "mdi:gauge"
        return "mdi:gauge-full"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        product = next(
            (
                p
                for p in self.coordinator.data
                if p["serial_number"] == self.product_serial_number and p["isConnected"]
            ),
            None,
        )
        self._update_state(product["indicator"].get("qte_eau_chaude") if product else None)
        super()._handle_coordinator_update()


class AldesMainRoomTemperatureEntity(BaseAldesSensorEntity):
    """Define an Aldes Main Room Temperature sensor."""

    def __init__(self, coordinator, config_entry, product_serial_number, reference, modem):
        super().__init__(coordinator, config_entry, product_serial_number, reference, modem)
        self._attr_device_class = "temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.product_serial_number)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.product_serial_number}",
            model=FRIENDLY_NAMES[self.reference],
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_main_room_temperature"

    @property
    def name(self) -> str:
        """Return a name for this entity."""
        return "Main Room Temperature"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        product = next(
            (
                p
                for p in self.coordinator.data
                if p["serial_number"] == self.product_serial_number and p["isConnected"]
            ),
            None,
        )
        self._update_state(product["indicator"].get("tmp_principal") if product else None)
        super()._handle_coordinator_update()
