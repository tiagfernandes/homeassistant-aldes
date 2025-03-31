"""Support for the Aldes sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, FRIENDLY_NAMES, MANUFACTURER
from .entity import AldesEntity, ThermostatApiEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    # Collect thermostat sensors
    sensors.extend(
        [
            AldesThermostatSensorEntity(
                coordinator,
                entry,
                thermostat,
            )
            for thermostat in coordinator.data.indicator.thermostats
        ]
    )

    # Collect Main Room Temperature sensor
    sensors.append(
        AldesMainRoomTemperatureEntity(
            coordinator,
            entry,
        )
    )

    # Collect water entities if AquaAir reference
    if coordinator.data.reference == "TONE_AQUA_AIR":
        sensors.append(
            AldesWaterEntity(
                coordinator,
                entry,
            )
        )

    async_add_entities(sensors)


class BaseAldesSensorEntity(AldesEntity, SensorEntity):
    """Base class for Aldes sensors with common attributes and methods."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry)
        self._state: Any | None = None

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

    thermostat: ThermostatApiEntity

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
        thermostat: ThermostatApiEntity,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry)
        self.thermostat = thermostat
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.thermostat.id))},
            manufacturer=MANUFACTURER,
            name=(
                f"Thermostat {self.thermostat.name}"
                if self.thermostat.name
                else f"Thermostat {self.thermostat.id}"
            ),
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.thermostat.id}_{self.thermostat.name}_temperature"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return f"Température {self.thermostat.name}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        thermostat = next(
            (
                t
                for t in self.coordinator.data.indicator.thermostats
                if t.id == self.thermostat.id
            ),
            None,
        )
        self._update_state(thermostat.current_temperature if thermostat else None)
        super()._handle_coordinator_update()


class AldesWaterEntity(BaseAldesSensorEntity):
    """Define an Aldes Water Quantity sensor."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry)
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_hot_water_quantity"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Quantité d'eau chaude"

    @property
    def icon(self) -> str:
        """Return an icon based on water level."""
        low_threshold = 25
        medium_threshold = 50
        high_threshold = 75

        if self._state is None or not isinstance(self._state, int | float):
            return "mdi:water-boiler"
        if self._state <= low_threshold:
            return "mdi:gauge-empty"
        if self._state <= medium_threshold:
            return "mdi:gauge-low"
        if self._state <= high_threshold:
            return "mdi:gauge"
        return "mdi:gauge-full"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        quantity = min(100, max(self.coordinator.data.indicator.hot_water_quantity, 0))

        self._update_state(quantity if self.coordinator.data.is_connected else None)
        super()._handle_coordinator_update()


class AldesMainRoomTemperatureEntity(BaseAldesSensorEntity):
    """Define an Aldes Main Room Temperature sensor."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry)
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_main_room_temperature"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Température de la pièce principale"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._update_state(
            self.coordinator.data.indicator.main_temperature
            if self.coordinator.data.is_connected
            else None
        )
        super()._handle_coordinator_update()
