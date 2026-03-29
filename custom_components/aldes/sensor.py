"""Support for the Aldes sensors."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    FRIENDLY_NAMES,
    MANUFACTURER,
    STATISTICS_UPDATE_INTERVAL,
    WATER_LEVEL_THRESHOLDS,
)
from .entity import AldesEntity, DeviceContext, ThermostatApiEntity
from .models import ApiHealthState, ThermostatApiEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config_entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []

    for device_key, device in (coordinator.data or {}).items():
        if not device or not device.indicator:
            continue
        context = DeviceContext(
            device_key=device_key,
            device=device,
            config_entry=entry,
        )

        # Collect thermostat sensors
        sensors.extend(
            [
                AldesThermostatSensorEntity(
                    coordinator,
                    context,
                    thermostat,
                )
                for thermostat in device.indicator.thermostats
            ]
        )

        # Collect Main Room Temperature sensor
        sensors.append(
            AldesMainRoomTemperatureEntity(
                coordinator,
                context,
            )
        )

        # Add filter sensor (always present)
        sensors.append(
            AldesFilterDateSensorEntity(
                coordinator,
                context,
            )
        )

        # Add last updated sensor
        sensors.append(
            AldesLastUpdatedSensorEntity(
                coordinator,
                context,
            )
        )

        # Add AquaAir specific sensors
        is_aqua_air = device.reference == "TONE_AQUA_AIR"
        if is_aqua_air:
            sensors.append(
                AldesWaterEntity(
                    coordinator,
                    context,
                )
            )

        # Add statistics sensors
        statistics_sensors = _create_statistics_sensors(
            coordinator, context, is_aqua_air=is_aqua_air
        )
        sensors.extend(statistics_sensors)

        # Add planning sensors (for all models)
        sensors.extend(
            [
                AldesPlanningEntity(
                    coordinator,
                    context,
                    "heating_prog_a",
                    "week_planning",
                ),
                AldesPlanningEntity(
                    coordinator,
                    context,
                    "heating_prog_b",
                    "week_planning2",
                ),
                AldesPlanningEntity(
                    coordinator,
                    context,
                    "cooling_prog_c",
                    "week_planning3",
                ),
                AldesPlanningEntity(
                    coordinator,
                    context,
                    "cooling_prog_d",
                    "week_planning4",
                ),
            ]
        )

        # Add holidays and frost protection sensors
        sensors.extend(
            [
                AldesHolidaysStartSensor(coordinator, context),
                AldesHolidaysEndSensor(coordinator, context),
                AldesHorsGelSensor(coordinator, context),
            ]
        )

        # Add diagnostic sensors
        sensors.extend(
            [
                AldesApiHealthSensor(coordinator, context),
                AldesDeviceInfoSensor(coordinator, context),
                AldesThermostatsCountSensor(coordinator, context),
                AldesTemperatureLimitsSensor(coordinator, context),
                AldesSettingsSensor(coordinator, context),
            ]
        )

    async_add_entities(sensors)


def _create_statistics_sensors(
    coordinator: AldesDataUpdateCoordinator,
    context: DeviceContext,
    *,
    is_aqua_air: bool,
) -> list[SensorEntity]:
    """Create statistics sensors based on device type."""
    sensors = []

    # Add ECS sensors only for AquaAir
    if is_aqua_air:
        sensors.extend(
            [
                AldesECSConsumptionSensor(coordinator, context),
                AldesECSCostSensor(coordinator, context),
            ]
        )

    # Add heating and cooling sensors for all models
    sensors.extend(
        [
            AldesHeatingConsumptionSensor(coordinator, context),
            AldesHeatingCostSensor(coordinator, context),
            AldesCoolingConsumptionSensor(coordinator, context),
            AldesCoolingCostSensor(coordinator, context),
        ]
    )

    return sensors


class BaseAldesSensorEntity(AldesEntity, SensorEntity):
    """Base class for Aldes sensors with common attributes and methods."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, context)
        self._state: Any | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_identifier)},
            manufacturer=MANUFACTURER,
            name=f"{FRIENDLY_NAMES[self.reference]} {self.device_identifier}",
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
        context: DeviceContext,
        thermostat: ThermostatApiEntity,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, context)
        self.thermostat = thermostat
        self._attr_unique_id = (
            f"{self.thermostat.id}_{self.thermostat.name}_temperature"
        )
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        identifier = str(self.thermostat.id)
        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer=MANUFACTURER,
            name=(
                f"Thermostat {self.thermostat.name}"
                if self.thermostat.name
                else f"Thermostat {self.thermostat.id}"
            ),
            via_device=(DOMAIN, self.device_identifier),
        )

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return f"Température {self.thermostat.name}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        device = self._get_device()
        if not device or not device.indicator:
            _LOGGER.debug("Coordinator data is None, skipping update")
            return

        device = self._get_device()
        if not device or not device.indicator:
            return

        thermostat = next(
            (
                t
                for t in device.indicator.thermostats
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
        context: DeviceContext,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, context)
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_hot_water_quantity"

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
        device = self._get_device()
        if device is None or device.indicator is None:
            self._update_state(None)
        else:
            quantity = min(
                100, max(device.indicator.hot_water_quantity, 0)
            )
            self._update_state(quantity if device.is_connected else None)
        super()._handle_coordinator_update()


class AldesMainRoomTemperatureEntity(BaseAldesSensorEntity):
    """Define an Aldes Main Room Temperature sensor."""

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, context)
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_main_room_temperature"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Température de la pièce principale"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        device = self._get_device()
        if device is None or device.indicator is None:
            self._update_state(None)
        else:
            self._update_state(
                device.indicator.main_temperature
                if device.is_connected
                else None
            )
        super()._handle_coordinator_update()


class AldesPlanningEntity(BaseAldesSensorEntity):
    """Sensor entity for weekly planning data."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
        planning_type: str,
        planning_key: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, context)
        self.planning_type = planning_type
        self.planning_key = planning_key

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_planning_{self.planning_type}"

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
        if "cooling" in self.planning_type:
            return "mdi:snowflake"
        return "mdi:calendar-week"

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        device = self._get_device()
        if not device:
            return "unavailable"

        try:
            planning = getattr(device, self.planning_key, None)
        except Exception:
            _LOGGER.exception("Error getting planning state %s", self.planning_type)
            return "error"
        else:
            if planning and isinstance(planning, list):
                return f"{len(planning)} items"
            return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with planning data."""
        device = self._get_device()
        if not device:
            return {}

        try:
            planning = getattr(device, self.planning_key, None)
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
            if not planning:
                return {}
            commands = [
                item if isinstance(item, str) else item.get("command")
                for item in planning
                if isinstance(item, str | dict)
            ]
            commands = [c for c in commands if c]
            return {
                "planning_data": commands,
                "item_count": len(commands),
            }


def _parse_utc_to_local(timestamp_str: str | None) -> datetime | None:
    """Parse UTC timestamp string and convert to local timezone."""
    if not timestamp_str:
        return None

    try:
        utc_dt = datetime.fromisoformat(timestamp_str)
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
        return f"{self.device_identifier}_filter_last_change"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Date dernier changement filtre"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        device = self._get_device()
        timestamp = (
            device.date_last_filter_update
            if device
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
        return f"{self.device_identifier}_last_updated"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Dernière mise à jour"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        device = self._get_device()
        timestamp = device.last_updated_date if device else None
        self._update_state(_parse_utc_to_local(timestamp))
        super()._handle_coordinator_update()


class BaseStatisticsSensor(BaseAldesSensorEntity):
    """Base class for statistics sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _statistics_data: list[Any] | dict[str, Any] | None = None
    _fetch_task: Any | None = None
    _suggested_object_id_suffix: str

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, context)
        self._attr_suggested_object_id = (
            f"{self._suggested_object_id_suffix}_{self.device_identifier}"
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()

        # Start statistics fetch only after Home Assistant is fully started
        # to avoid slowing down the startup process
        @callback
        def _start_statistics_fetch(_event: Any) -> None:
            """Start fetching statistics after HA startup."""
            self._fetch_task = self.hass.async_create_task(
                self._fetch_statistics_loop()
            )

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, _start_statistics_fetch
        )

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
            except Exception:
                _LOGGER.exception("Error in statistics fetch loop")
                await asyncio.sleep(STATISTICS_UPDATE_INTERVAL)

    async def _fetch_statistics(self) -> None:
        """Fetch statistics from API."""
        try:
            # Get current month's data
            end_date = datetime.now(tz=UTC)
            start_date = end_date.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )

            start_str = start_date.strftime("%Y%m%d%H%M%SZ")
            end_str = end_date.strftime("%Y%m%d%H%M%SZ")

            self._statistics_data = await self.coordinator.api.get_statistics(
                self.modem, start_str, end_str, "month"
            )

            self.async_write_ha_state()
        except Exception:
            _LOGGER.exception("Error fetching statistics")

    def _get_latest_stat(self) -> dict[str, Any] | None:
        """Get the most recent statistic entry."""
        if not self._statistics_data:
            return None

        # Handle list format (direct array of stats)
        if isinstance(self._statistics_data, list):
            return self._statistics_data[-1] if self._statistics_data else None

        # Handle dict format with statArray key
        if isinstance(self._statistics_data, dict):
            stat_array = self._statistics_data.get("statArray", [])
            return stat_array[-1] if stat_array else None

        return None


class AldesECSConsumptionSensor(BaseStatisticsSensor):
    """Sensor for ECS (hot water) consumption."""

    _suggested_object_id_suffix = "ecs_consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-boiler"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_ecs_consumption"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Consommation ECS (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "ecs" in latest:
            consumption = latest["ecs"].get("consumption")
            if consumption is not None:
                return consumption
        return None


class AldesECSCostSensor(BaseStatisticsSensor):
    """Sensor for ECS (hot water) cost."""

    _suggested_object_id_suffix = "ecs_cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_ecs_cost"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Coût ECS (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "ecs" in latest:
            cost = latest["ecs"].get("cost")
            if cost is not None:
                return cost
        return None


class AldesHeatingConsumptionSensor(BaseStatisticsSensor):
    """Sensor for heating consumption."""

    _suggested_object_id_suffix = "heating_consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:radiator"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_heating_consumption"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Consommation Chauffage (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "chauffage" in latest:
            consumption = latest["chauffage"].get("consumption")
            if consumption is not None:
                return consumption
        return None


class AldesHeatingCostSensor(BaseStatisticsSensor):
    """Sensor for heating cost."""

    _suggested_object_id_suffix = "heating_cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_heating_cost"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Coût Chauffage (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "chauffage" in latest:
            cost = latest["chauffage"].get("cost")
            if cost is not None:
                return cost
        return None


class AldesCoolingConsumptionSensor(BaseStatisticsSensor):
    """Sensor for cooling consumption."""

    _suggested_object_id_suffix = "cooling_consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:snowflake"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_cooling_consumption"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Consommation Climatisation (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "clim" in latest:
            consumption = latest["clim"].get("consumption")
            if consumption is not None:
                return consumption
        return None


class AldesCoolingCostSensor(BaseStatisticsSensor):
    """Sensor for cooling cost."""

    _suggested_object_id_suffix = "cooling_cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_cooling_cost"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Coût Climatisation (mois en cours)"

    @property
    def native_value(self) -> float | None:
        """Return the state."""
        latest = self._get_latest_stat()
        if latest and "clim" in latest:
            cost = latest["clim"].get("cost")
            if cost is not None:
                return cost
        return None


class AldesHolidaysStartSensor(BaseAldesSensorEntity):
    """Sensor for holidays start date."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-start"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_holidays_start"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Début vacances"

    @property
    def native_value(self) -> datetime | None:
        """Return the state."""
        device = self._get_device()
        if device is None or not device.holidays_start:
            return None
        try:
            # Parse "2025-12-11 20:57:06Z" format
            return datetime.strptime(
                device.holidays_start, "%Y-%m-%d %H:%M:%SZ"
            ).replace(tzinfo=dt_util.UTC)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Failed to parse holidays_start: %s",
                device.holidays_start if device else None,
            )
            return None


class AldesHolidaysEndSensor(BaseAldesSensorEntity):
    """Sensor for holidays end date."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-end"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_holidays_end"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Fin vacances"

    @property
    def native_value(self) -> datetime | None:
        """Return the state."""
        device = self._get_device()
        if device is None or not device.holidays_end:
            return None
        try:
            # Parse "2025-12-11 20:57:06Z" format
            return datetime.strptime(device.holidays_end, "%Y-%m-%d %H:%M:%SZ").replace(
                tzinfo=dt_util.UTC
            )
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Failed to parse holidays_end: %s",
                device.holidays_end if device else None,
            )
            return None


class AldesHorsGelSensor(BaseAldesSensorEntity):
    """Sensor for frost protection mode."""

    _attr_device_class = None
    _attr_icon = "mdi:snowflake-alert"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_hors_gel"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Mode hors gel"

    @property
    def native_value(self) -> str:
        """Return the state."""
        device = self._get_device()
        if device is None:
            return "unknown"
        return "Actif" if device.hors_gel else "Inactif"


class AldesApiHealthSensor(BaseAldesSensorEntity):
    """Sensor for API connectivity status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [state.value for state in ApiHealthState]

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_api_health"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "État API Aldes"

    @property
    def native_value(self) -> str:
        """Return the state."""
        return self.coordinator.api.health_state.value

    @property
    def icon(self) -> str:
        """Return a dynamic icon based on the health state."""
        state_map = {
            ApiHealthState.ONLINE: "mdi:cloud-check",
            ApiHealthState.RETRYING: "mdi:cloud-sync",
            ApiHealthState.DEGRADED: "mdi:cloud-alert",
            ApiHealthState.OFFLINE: "mdi:cloud-off-outline",
        }
        return state_map.get(self.coordinator.api.health_state, "mdi:cloud-question")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with diagnostic data."""
        try:
            return self.coordinator.api.get_diagnostic_info()
        except Exception as e:
            _LOGGER.warning("Error getting API diagnostic info: %s", e)
            return {}


class AldesDeviceInfoSensor(BaseAldesSensorEntity):
    """Sensor for device information and diagnostics."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information"
    _attr_entity_registry_visible_default = False

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_device_info"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Informations Appareil"

    @property
    def native_value(self) -> str:
        """Return the state."""
        device = self._get_device()
        if device is None:
            return "unknown"
        return f"{device.reference} ({device.type})"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with device details."""
        device = self._get_device()
        if device is None:
            return {}

        return {
            "reference": device.reference,
            "type": device.type,
            "serial_number": device.serial_number,
            "modem": device.modem,
            "is_connected": device.is_connected,
            "thermostats_count": len(device.indicator.thermostats),
            "has_filter": device.has_filter,
            "filter_wear": device.filter_wear,
        }


class AldesThermostatsCountSensor(BaseAldesSensorEntity):
    """Sensor for thermostat count."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:thermometer"
    _attr_entity_registry_visible_default = False

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_thermostats_count"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Nombre de Thermostats"

    @property
    def native_value(self) -> int:
        """Return the state."""
        device = self._get_device()
        if device is None:
            return 0
        return len(device.indicator.thermostats)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with thermostat details."""
        device = self._get_device()
        if device is None:
            return {}

        thermostats = []
        thermostats = [
            {
                "id": t.id,
                "name": t.name,
                "number": t.number,
                "current_temperature": t.current_temperature,
                "temperature_set": t.temperature_set,
            }
            for t in device.indicator.thermostats
        ]

        return {"thermostats": thermostats}


class AldesTemperatureLimitsSensor(BaseAldesSensorEntity):
    """Sensor for temperature limits (heating and cooling)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:thermometer-lines"
    _attr_entity_registry_visible_default = False

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_temperature_limits"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Limites de Température"

    @property
    def native_value(self) -> str:
        """Return the state."""
        device = self._get_device()
        if device is None:
            return "unknown"
        indicator = device.indicator
        return (
            f"H: {indicator.fmist}°C-{indicator.fmast}°C, "
            f"C: {indicator.cmist}°C-{indicator.cmast}°C"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with temperature limits."""
        device = self._get_device()
        if device is None:
            return {}

        indicator = device.indicator
        return {
            "heat_min": indicator.fmist,
            "heat_max": indicator.fmast,
            "cool_min": indicator.cmist,
            "cool_max": indicator.cmast,
            "main_temperature": indicator.main_temperature,
        }


class AldesSettingsSensor(BaseAldesSensorEntity):
    """Sensor for device settings."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cog"
    _attr_entity_registry_visible_default = False

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.device_identifier}_settings"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return "Paramètres Appareil"

    @property
    def native_value(self) -> str:
        """Return the state."""
        device = self._get_device()
        if device is None:
            return "unknown"
        settings = device.indicator.settings
        return "configured" if settings else "unconfigured"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes with settings."""
        device = self._get_device()
        if device is None:
            return {}

        settings = device.indicator.settings
        return {
            "household_composition": str(settings.people) if settings.people else None,
            "antilegio_cycle": settings.antilegio,
            "kwh_creuse": settings.kwh_creuse,
            "kwh_pleine": settings.kwh_pleine,
        }
