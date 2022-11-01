"""Support for the AldesConnect sensors."""
from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN
from .entity import AldesConnectEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add AldesConnect sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors: list[AldesConnectClimateEntity] = []

    for product in coordinator.data:
        for thermostat in product["indicator"]["thermostats"]:
            sensors.append(
                AldesConnectClimateEntity(
                    coordinator,
                    entry,
                    product["serial_number"],
                    product["reference"],
                    thermostat["ThermostatId"],
                )
            )

    async_add_entities(sensors)


class AldesConnectClimateEntity(AldesConnectEntity, ClimateEntity):
    """Define an AldesConnect sensor."""

    def __init__(
        self, coordinator, config_entry, product_serial_number, reference, thermostat_id
    ):
        super().__init__(coordinator, config_entry, product_serial_number, reference)
        self.thermostat_id = thermostat_id
        self._attr_device_class = "temperature"
        self._attr_temperature_unit = TEMP_CELSIUS
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def device_info(self):
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.thermostat_id)},
        )

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{DOMAIN}_{self.product_serial_number}_{self.thermostat_id}_climate"

    @property
    def name(self):
        """Return a name to use for this entity."""
        for product in self.coordinator.data:
            if product["serial_number"] == self.product_serial_number:
                for thermostat in product["indicator"]["thermostats"]:
                    if thermostat["ThermostatId"] == self.thermostat_id:
                        return f"{thermostat['Name']} climate"
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
            if product["serial_number"] == self.product_serial_number:
                if product["indicator"]["current_air_mode"] == "C":
                    self._attr_hvac_mode = HVACMode.HEAT
                for thermostat in product["indicator"]["thermostats"]:
                    if thermostat["ThermostatId"] == self.thermostat_id:
                        self._attr_target_temperature = thermostat["TemperatureSet"]
                        self._attr_current_temperature = thermostat[
                            "CurrentTemperature"
                        ]
