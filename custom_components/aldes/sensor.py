"""Support for the Aldes sensors."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FRIENDLY_NAMES, MANUFACTURER
from .entity import AldesEntity, ThermostatApiEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Constants
STATISTICS_UPDATE_INTERVAL = 3600  # Update every hour (in seconds)
WATER_LEVEL_THRESHOLDS = {
    "low": 25,
    "medium": 50,
    "high": 75,
}


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

    # Add AquaAir specific sensors
    is_aqua_air = coordinator.data.reference == "TONE_AQUA_AIR"
    if is_aqua_air:
        sensors.append(AldesWaterEntity(coordinator, entry))

    # Add statistics sensors
    statistics_sensors = _create_statistics_sensors(coordinator, entry, is_aqua_air)
    sensors.extend(statistics_sensors)

    # Add planning sensors (for all models)
    sensors.extend(
        [
            AldesPlanningEntity(coordinator, entry, "heating_prog_a", "week_planning"),
            AldesPlanningEntity(coordinator, entry, "heating_prog_b", "week_planning2"),
            AldesPlanningEntity(coordinator, entry, "cooling_prog_c", "week_planning3"),
            AldesPlanningEntity(coordinator, entry, "cooling_prog_d", "week_planning4"),
        ]
    )

    # Add kWh price sensors (read-only)
    sensors.extend(
        [
            AldesKwhCreuseSensor(coordinator, entry),
            AldesKwhPleineSensor(coordinator, entry),
        ]
    )

    async_add_entities(sensors)


def _create_statistics_sensors(
    coordinator: AldesDataUpdateCoordinator,
    entry: ConfigEntry,
    is_aqua_air: bool,
) -> list[SensorEntity]:
    """Create statistics sensors based on device type."""
    sensors = []

    # Add ECS sensors only for AquaAir
    if is_aqua_air:
        sensors.extend(
            [
                AldesECSConsumptionSensor(coordinator, entry),
                AldesECSCostSensor(coordinator, entry),
            ]
        )

    # Add heating and cooling sensors for all models
    sensors.extend(
        [
            AldesHeatingConsumptionSensor(coordinator, entry),
            AldesHeatingCostSensor(coordinator, entry),
            AldesCoolingConsumptionSensor(coordinator, entry),
            AldesCoolingCostSensor(coordinator, entry),
        ]
    )

    return sensors


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
        if self._state is None or not isinstance(self._state, int | float):
            return "mdi:water-boiler"

        if self._state <= WATER_LEVEL_THRESHOLDS["low"]:
            return "mdi:gauge-empty"
        if self._state <= WATER_LEVEL_THRESHOLDS["medium"]:
            return "mdi:gauge-low"
        if self._state <= WATER_LEVEL_THRESHOLDS["high"]:
            return "mdi:gauge"
        return "mdi:gauge-full"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        if self.coordinator.data is None:
            self._update_state(None)
        else:
            quantity = min(
                100, max(self.coordinator.data.indicator.hot_water_quantity, 0)
            )
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
        if self.coordinator.data is None:
            self._update_state(None)
        else:
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
            return "unavailable"

        try:
            planning = getattr(self.coordinator.data, self.planning_key, None)
            if planning and isinstance(planning, list):
                return f"{len(planning)} items"
            return "unknown"
        except Exception as e:
            _LOGGER.error("Error getting planning state %s: %s", self.planning_type, e)
            return "error"

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
                    if isinstance(item, str | dict)
                ]
                commands = [c for c in commands if c]
                result = {
                    "planning_data": commands,
                    "item_count": len(commands),
                }
            else:
                result = {}
        except Exception as e:
            _LOGGER.error(
                "Error getting planning attributes %s: %s", self.planning_type, e
            )
            return {}
        else:
            return result


def _parse_utc_to_local(timestamp_str: str | None) -> datetime | None:
    """Parse UTC timestamp string and convert to local timezone."""
    if not timestamp_str:
        return None

    try:
        utc_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt_util.as_local(utc_dt)
    except (ValueError, AttributeError) as e:
        _LOGGER.warning("Failed to parse timestamp '%s': %s", timestamp_str, e)
        return None


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
        timestamp = (
            self.coordinator.data.date_last_filter_update
            if self.coordinator.data
            else None
        )
        self._update_state(_parse_utc_to_local(timestamp))
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
        timestamp = (
            self.coordinator.data.last_updated_date if self.coordinator.data else None
        )
        self._update_state(_parse_utc_to_local(timestamp))
        super()._handle_coordinator_update()


class BaseStatisticsSensor(BaseAldesSensorEntity):
    """Base class for statistics sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _statistics_data: dict[str, Any] | None = None
    _fetch_task: Any | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        self._fetch_task = self.hass.async_create_task(self._fetch_statistics_loop())

    async def async_will_remove_from_hass(self) -> None:
        """Cancel the update task when entity is removed."""
        if self._fetch_task:
            self._fetch_task.cancel()
        await super().async_will_remove_from_hass()

    async def _fetch_statistics_loop(self) -> None:
        """Fetch statistics periodically."""
        while True:
            try:
                await self._fetch_statistics()
                await asyncio.sleep(STATISTICS_UPDATE_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in statistics fetch loop: %s", e)
                await asyncio.sleep(STATISTICS_UPDATE_INTERVAL)

    async def _fetch_statistics(self) -> None:
        """Fetch statistics from API."""
        try:
            # Get current month's data
            end_date = datetime.utcnow()
            start_date = end_date.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

            start_str = start_date.strftime("%Y%m%d%H%M%SZ")
            end_str = end_date.strftime("%Y%m%d%H%M%SZ")

            self._statistics_data = await self.coordinator.api.get_statistics(
                self.modem, start_str, end_str, "month"
            )

            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Error fetching statistics: %s", e)

    def _get_latest_stat(self) -> dict[str, Any] | None:
        """Get the most recent statistic entry."""
        if not self._statistics_data or "statArray" not in self._statistics_data:
            return None

        stat_array = self._statistics_data.get("statArray", [])
        if not stat_array:
            return None

        # Return the last entry (most recent)
        return stat_array[-1]


class AldesECSConsumptionSensor(BaseStatisticsSensor):
    """Sensor for ECS (hot water) consumption."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = "total"
    _attr_icon = "mdi:water-boiler"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_ecs_consumption"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Consommation ECS (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "ecs" in latest:
            return latest["ecs"].get("consumption")
        return None


class AldesECSCostSensor(BaseStatisticsSensor):
    """Sensor for ECS (hot water) cost."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = "total"
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_ecs_cost"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Coût ECS (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "ecs" in latest:
            return latest["ecs"].get("cost")
        return None


class AldesHeatingConsumptionSensor(BaseStatisticsSensor):
    """Sensor for heating consumption."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = "total"
    _attr_icon = "mdi:radiator"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_heating_consumption"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Consommation Chauffage (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "chauffage" in latest:
            return latest["chauffage"].get("consumption")
        return None


class AldesHeatingCostSensor(BaseStatisticsSensor):
    """Sensor for heating cost."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = "total"
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_heating_cost"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Coût Chauffage (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "chauffage" in latest:
            return latest["chauffage"].get("cost")
        return None


class AldesCoolingConsumptionSensor(BaseStatisticsSensor):
    """Sensor for cooling consumption."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = "total"
    _attr_icon = "mdi:snowflake"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_cooling_consumption"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Consommation Climatisation (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "clim" in latest:
            return latest["clim"].get("consumption")
        return None


class AldesCoolingCostSensor(BaseStatisticsSensor):
    """Sensor for cooling cost."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = "total"
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.serial_number}_cooling_cost"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Coût Climatisation (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "clim" in latest:
            return latest["clim"].get("cost")
        return None


class AldesKwhCreuseSensor(BaseAldesSensorEntity):
    """Sensor for off-peak hour electricity price (read-only)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = None
    _attr_icon = "mdi:currency-eur"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        if (
            self.coordinator.data is None
            or self.coordinator.data.indicator is None
            or self.coordinator.data.indicator.settings is None
        ):
            return None
        return self.coordinator.data.indicator.settings.kwh_creuse


class AldesKwhPleineSensor(BaseAldesSensorEntity):
    """Sensor for peak hour electricity price (read-only)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = None
    _attr_icon = "mdi:currency-eur"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        if (
            self.coordinator.data is None
            or self.coordinator.data.indicator is None
            or self.coordinator.data.indicator.settings is None
        ):
            return None
        return self.coordinator.data.indicator.settings.kwh_pleine
