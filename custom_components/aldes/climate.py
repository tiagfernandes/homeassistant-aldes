"""Support for the Aldes sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    ClimateEntity,
)
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, AirMode
from .entity import AldesEntity, ThermostatApiEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

TEMPERATURE_REDUCE_ECO = 2


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
        """Innitialize."""
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
        return DeviceInfo(identifiers={(DOMAIN, str(self.thermostat.id))})

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self.thermostat.id}_climate"

    @property
    def name(self) -> str:
        """Return the name of this entity."""
        return f"{self.thermostat.name} climate"

    @property
    def min_temp(self) -> float | None:
        """Get the minimum temperature based on the current mode."""
        return self._get_temperature("min")

    @property
    def max_temp(self) -> float | None:
        """Get the maximum temperature based on the current mode."""
        return self._get_temperature("max")

    def _get_temperature(self, temp_type: str) -> float | None:
        """Calculate the min or max temperature."""
        if self.coordinator.data is None:
            return None

        mode = self.coordinator.data.indicator.current_air_mode
        temp_key = "cmist" if temp_type == "min" else "cmast"

        if mode in [AirMode.COOL_COMFORT, AirMode.COOL_BOOST]:
            temp_key = "fmist" if temp_type == "min" else "fmast"

        temp = self.coordinator.data.indicator.__getattribute__(temp_key)
        return temp - TEMPERATURE_REDUCE_ECO if mode == AirMode.HEAT_ECO else temp

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update attributes based on coordinator data."""
        thermostat = self.thermostat

        if not thermostat or not self.coordinator.data.is_connected:
            self._attr_current_temperature = None
            return

        self._attr_target_temperature = thermostat.temperature_set
        self._attr_current_temperature = thermostat.current_temperature

        air_mode = self.coordinator.data.indicator.current_air_mode
        self._attr_hvac_mode = self._determine_hvac_mode(air_mode)
        self._attr_hvac_action = self._determine_hvac_action(air_mode)

    def _determine_hvac_mode(self, air_mode: AirMode) -> HVACMode:
        """Determine HVAC mode from air mode."""
        return {
            AirMode.OFF: HVACMode.OFF,
            AirMode.HEAT_COMFORT: HVACMode.HEAT,
            AirMode.HEAT_ECO: HVACMode.HEAT,
            AirMode.HEAT_PROG_A: HVACMode.HEAT,
            AirMode.HEAT_PROG_B: HVACMode.HEAT,
            AirMode.COOL_COMFORT: HVACMode.COOL,
            AirMode.COOL_BOOST: HVACMode.COOL,
            AirMode.COOL_PROG_A: HVACMode.COOL,
            AirMode.COOL_PROG_B: HVACMode.COOL,
        }.get(air_mode, HVACMode.AUTO)

    def _determine_hvac_action(self, air_mode: AirMode) -> HVACAction:
        """Determine HVAC action."""
        if air_mode in [AirMode.HEAT_COMFORT, AirMode.HEAT_ECO] and (
            self._attr_current_temperature is not None
            and self._attr_target_temperature is not None
        ):
            return (
                HVACAction.HEATING
                if self._attr_current_temperature < self._attr_target_temperature
                else HVACAction.IDLE
            )
        if air_mode in [AirMode.COOL_COMFORT, AirMode.COOL_BOOST] and (
            self._attr_current_temperature is not None
            and self._attr_target_temperature is not None
        ):
            return (
                HVACAction.COOLING
                if self._attr_current_temperature > self._attr_target_temperature
                else HVACAction.IDLE
            )
        return HVACAction.OFF

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        target_temperature = kwargs.get(ATTR_TEMPERATURE)

        await self.coordinator.api.set_target_temperature(
            self.modem, self.thermostat.id, self.thermostat.name, target_temperature
        )
        self._attr_target_temperature = kwargs.get(ATTR_TEMPERATURE)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        modes_map = {
            HVACMode.OFF: AirMode.OFF,
            HVACMode.HEAT: AirMode.HEAT_COMFORT,
            HVACMode.COOL: AirMode.COOL_COMFORT,
        }
        mode = modes_map.get(hvac_mode)
        if mode:
            await self.coordinator.api.change_mode(
                self.modem, mode.value, is_for_hot_water=False
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
