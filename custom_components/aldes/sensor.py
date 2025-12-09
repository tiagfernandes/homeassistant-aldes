"""Support for the Aldes sensors."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FRIENDLY_NAMES, MANUFACTURER
from .entity import AldesEntity, ThermostatApiEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

import logging

_LOGGER = logging.getLogger(__name__)


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

    # Add filter sensor (always present)
    sensors.append(
        AldesFilterDateSensorEntity(
            coordinator,
            entry,
        )
    )

    # Add last updated sensor
    sensors.append(
        AldesLastUpdatedSensorEntity(
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

        # Add planning sensors
        sensors.extend(
            [
                AldesPlanningEntity(
                    coordinator, entry, "heating_prog_a", "week_planning"
                ),
                AldesPlanningEntity(
                    coordinator, entry, "heating_prog_b", "week_planning2"
                ),
                AldesPlanningEntity(
                    coordinator, entry, "cooling_prog_c", "week_planning3"
                ),
                AldesPlanningEntity(
                    coordinator, entry, "cooling_prog_d", "week_planning4"
                ),
            ]
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

        if not self.coordinator.data:
            _LOGGER.debug("Coordinator data is None, skipping update")
            return

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


class AldesPlanningEntity(BaseAldesSensorEntity):
    """Sensor entity for weekly planning data."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
        planning_type: str,
        planning_key: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, config_entry)
        self.planning_type = planning_type
        self.planning_key = planning_key

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_planning_{self.planning_type}"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        names = {
            "heating_prog_a": "Planning Chauffage Programme A",
            "heating_prog_b": "Planning Chauffage Programme B",
            "cooling_prog_c": "Planning Climatisation Programme C",
            "cooling_prog_d": "Planning Climatisation Programme D",
        }
        return names.get(self.planning_type, "Planning")

    @property
    def icon(self) -> str:
        """Return the icon."""
        if "heating" in self.planning_type:
            return "mdi:fire"
        elif "cooling" in self.planning_type:
            return "mdi:snowflake"
        return "mdi:calendar-week"

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        if not self.coordinator.data:
            return None

        try:
            planning = getattr(self.coordinator.data, self.planning_key, None)
            if planning and isinstance(planning, list):
                return f"{len(planning)} items"
            return None
        except Exception as e:
            _LOGGER.error("Error getting planning state %s: %s", self.planning_type, e)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with planning data."""
        if not self.coordinator.data:
            return {}

        try:
            planning = getattr(self.coordinator.data, self.planning_key, None)
            if planning:
                commands = [
                    item if isinstance(item, str) else item.get("command")
                    for item in planning
                    if (isinstance(item, str) or isinstance(item, dict))
                ]
                commands = [c for c in commands if c]
                return {
                    "planning_data": commands,
                    "item_count": len(commands),
                }
            return {}
        except Exception as e:
            _LOGGER.error(
                "Error getting planning attributes %s: %s", self.planning_type, e
            )
            return {}


class AldesFilterDateSensorEntity(BaseAldesSensorEntity):
    """Define an Aldes filter last change date sensor."""

    _attr_icon = "mdi:air-filter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_filter_last_change"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Date dernier changement filtre"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        if (
            self.coordinator.data is not None
            and self.coordinator.data.date_last_filter_update
        ):
            # Parse UTC timestamp and convert to datetime object
            try:
                utc_dt = datetime.fromisoformat(
                    self.coordinator.data.date_last_filter_update.replace("Z", "+00:00")
                )
                # Convert to Home Assistant timezone
                local_dt = dt_util.as_local(utc_dt)
                self._update_state(local_dt)
            except (ValueError, AttributeError) as e:
                _LOGGER.warning("Failed to parse filter date: %s", e)
                self._update_state(None)
        else:
            self._update_state(None)
        super()._handle_coordinator_update()


class AldesLastUpdatedSensorEntity(BaseAldesSensorEntity):
    """Define an Aldes last updated date sensor."""

    _attr_icon = "mdi:update"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_last_updated"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Dernière mise à jour"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        if (
            self.coordinator.data is not None
            and self.coordinator.data.last_updated_date
        ):
            # Parse UTC timestamp and convert to datetime object
            try:
                utc_dt = datetime.fromisoformat(
                    self.coordinator.data.last_updated_date.replace("Z", "+00:00")
                )
                # Convert to Home Assistant timezone
                local_dt = dt_util.as_local(utc_dt)
                self._update_state(local_dt)
            except (ValueError, AttributeError) as e:
                _LOGGER.warning("Failed to parse last updated date: %s", e)
                self._update_state(None)
        else:
            self._update_state(None)
        super()._handle_coordinator_update()
