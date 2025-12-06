"""Support for the Aldes sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import AirMode, DOMAIN, ECO_MODE_TEMPERATURE_OFFSET
from .entity import AldesEntity, ThermostatApiEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

from custom_components.aldes.api import CommandUid


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = [
        AldesClimateEntity(
            coordinator,
            entry,
            thermostat,
        )
        for thermostat in coordinator.data.indicator.thermostats
    ]

    async_add_entities(sensors)


class AldesClimateEntity(AldesEntity, ClimateEntity):
    """Define an Aldes climate entity."""

    coordinator: AldesDataUpdateCoordinator

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
        thermostat: ThermostatApiEntity,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            config_entry,
        )
        self.thermostat = thermostat
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        self._attr_target_temperature_step = 1
        self._attr_hvac_action = HVACAction.OFF

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.thermostat.id))},
            name=f"Thermostat {self.thermostat.id!s} {self.thermostat.name}",
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID to use for this entity."""
        return f"{self.thermostat.id}_{self.thermostat.name}_climate"

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name."""
        return f"Thermostat {self.thermostat.name}"

    @property
    def min_temp(self) -> float | None:
        """Get the minimum temperature based on the current mode."""
        return self._get_temperature("min")

    @property
    def max_temp(self) -> float | None:
        """Get the maximum temperature based on the current mode."""
        return self._get_temperature("max")

    def _get_temperature(self, temp_type: str) -> float | None:
        """Calculate the min or max temperature with ECO offset if applicable."""
        if self.coordinator.data is None:
            return None

        mode = self.coordinator.data.indicator.current_air_mode
        is_heating_mode = mode not in [AirMode.COOL_COMFORT, AirMode.COOL_BOOST]

        temp_key_map = {
            "min": ("cmist", "fmist"),  # (heating, cooling)
            "max": ("cmast", "fmast"),
        }
        heating_key, cooling_key = temp_key_map.get(temp_type, ("cmist", "fmist"))
        temp_key = heating_key if is_heating_mode else cooling_key

        temperature = getattr(self.coordinator.data.indicator, temp_key, None)

        # Apply ECO mode offset for heating modes
        if temperature is not None and mode == AirMode.HEAT_ECO:
            temperature = temperature - ECO_MODE_TEMPERATURE_OFFSET

        return temperature

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update attributes based on coordinator data."""
        thermostat = self._get_thermostat_by_id(self.thermostat.id)

        if not thermostat or not self.coordinator.data.is_connected:
            self._attr_current_temperature = None
            return

        self._attr_current_temperature = thermostat.current_temperature

        air_mode = self.coordinator.data.indicator.current_air_mode
        self._attr_hvac_mode = self._determine_hvac_mode(air_mode)
        self._attr_hvac_action = self._determine_hvac_action(air_mode)

        # ECO mode displays temperature offset for user clarity
        temperature_offset = (
            ECO_MODE_TEMPERATURE_OFFSET if air_mode == AirMode.HEAT_ECO else 0
        )
        self._attr_target_temperature = thermostat.temperature_set - temperature_offset

    def _get_thermostat_by_id(self, target_id: int) -> ThermostatApiEntity | None:
        """Return thermostat object by id."""
        return next(
            (
                thermostat
                for thermostat in self.coordinator.data.indicator.thermostats
                if thermostat.id == target_id
            ),
            None,
        )

    def _determine_hvac_mode(self, air_mode: AirMode) -> HVACMode:
        """Determine HVAC mode from air mode."""
        # Group modes by their HVAC equivalent
        mode_mapping = {
            AirMode.OFF: HVACMode.OFF,
            AirMode.HEAT_COMFORT: HVACMode.HEAT,
            AirMode.HEAT_ECO: HVACMode.HEAT,
            AirMode.HEAT_PROG_A: HVACMode.HEAT,
            AirMode.HEAT_PROG_B: HVACMode.HEAT,
            AirMode.COOL_COMFORT: HVACMode.COOL,
            AirMode.COOL_BOOST: HVACMode.COOL,
            AirMode.COOL_PROG_A: HVACMode.COOL,
            AirMode.COOL_PROG_B: HVACMode.COOL,
        }
        return mode_mapping.get(air_mode, HVACMode.AUTO)

    def _determine_hvac_action(self, air_mode: AirMode) -> HVACAction:
        """Determine HVAC action based on current vs target temperature."""
        # Return OFF if mode is OFF
        if air_mode == AirMode.OFF:
            return HVACAction.OFF

        # Check if temperatures are available
        if (
            self._attr_current_temperature is None
            or self._attr_target_temperature is None
        ):
            return HVACAction.OFF

        current_temperature = self._attr_current_temperature
        target_temperature = getattr(
            self, "_real_target", self._attr_target_temperature
        )

        # Heating modes
        if air_mode in [
            AirMode.HEAT_COMFORT,
            AirMode.HEAT_ECO,
            AirMode.HEAT_PROG_A,
            AirMode.HEAT_PROG_B,
        ]:
            return (
                HVACAction.HEATING
                if current_temperature < target_temperature
                else HVACAction.IDLE
            )

        # Cooling modes
        if air_mode in [
            AirMode.COOL_COMFORT,
            AirMode.COOL_BOOST,
            AirMode.COOL_PROG_A,
            AirMode.COOL_PROG_B,
        ]:
            return (
                HVACAction.COOLING
                if current_temperature > target_temperature
                else HVACAction.IDLE
            )

        return HVACAction.OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        target_temperature = kwargs.get(ATTR_TEMPERATURE)

        air_mode = self.coordinator.data.indicator.current_air_mode

        # ECO mode requires temperature adjustment for heat pump
        temperature_offset = (
            ECO_MODE_TEMPERATURE_OFFSET if air_mode == AirMode.HEAT_ECO else 0
        )
        pac_target = target_temperature + temperature_offset

        await self.coordinator.api.set_target_temperature(
            self.modem, self.thermostat.id, self.thermostat.name, pac_target
        )

        # Store internal value for display in Home Assistant
        self._attr_target_temperature = target_temperature

        # Update HVAC action immediately based on new target temperature
        self._attr_hvac_action = self._determine_hvac_action(air_mode)

        # Prevent coordinator from overwriting pending update
        self.coordinator.skip_next_update = True

        # Update Home Assistant state
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        hvac_to_air_mode = {
            HVACMode.OFF: AirMode.OFF,
            HVACMode.HEAT: AirMode.HEAT_COMFORT,
            HVACMode.COOL: AirMode.COOL_COMFORT,
        }
        air_mode = hvac_to_air_mode.get(hvac_mode)

        if air_mode is None:
            return

        await self.coordinator.api.change_mode(
            self.modem, air_mode.value, CommandUid.AIR_MODE
        )
        self._attr_hvac_mode = hvac_mode
        self.coordinator.skip_next_update = True
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on the climate device."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn off the climate device."""
        await self.async_set_hvac_mode(HVACMode.OFF)
