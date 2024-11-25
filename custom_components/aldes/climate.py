"""Support for the Aldes sensors."""
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_BOOST,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, ALDESMode
from .entity import AldesEntity

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
            product["serial_number"],
            product["reference"],
            product["modem"],
            thermostat["ThermostatId"],
        )
        for product in coordinator.data
        for thermostat in product["indicator"]["thermostats"]
    ]

    async_add_entities(sensors)


class AldesClimateEntity(AldesEntity, ClimateEntity):
    """Define an Aldes climate entity."""

    def __init__(
        self,
        coordinator,
        config_entry,
        product_serial_number,
        reference,
        modem,
        thermostat_id,
    ) -> None:
        super().__init__(
            coordinator, config_entry, product_serial_number, reference, modem
        )
        self.thermostat_id = thermostat_id
        self._attr_device_class = "temperature"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_target_temperature_step = 1
        self._attr_hvac_action = HVACAction.OFF
        self._attr_preset_mode = PRESET_COMFORT
        self._attr_preset_modes = [PRESET_COMFORT, PRESET_ECO, PRESET_BOOST]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(identifiers={(DOMAIN, self.thermostat_id)})

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        return f"{DOMAIN}_{self.thermostat_id}_climate"

    @property
    def name(self) -> str | None:
        """Return the name of this entity."""
        thermostat = self._get_thermostat()
        return f"{thermostat['Name']} climate" if thermostat else None

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
        product = self._get_product()
        if not product:
            return None

        mode = product["indicator"]["current_air_mode"]
        temp_key = "cmist" if temp_type == "min" else "cmast"

        if mode in [ALDESMode.COOL_COMFORT, ALDESMode.COOL_BOOST]:
            temp_key = "fmist" if temp_type == "min" else "fmast"

        temp = product["indicator"].get(temp_key)
        return temp - TEMPERATURE_REDUCE_ECO if mode == ALDESMode.HEAT_ECO else temp

    def _get_product(self) -> dict | None:
        """Retrieve the product for this thermostat."""
        return next(
            (p for p in self.coordinator.data if p["serial_number"] == self.product_serial_number), None
        )

    def _get_thermostat(self) -> dict | None:
        """Retrieve thermostat data."""
        product = self._get_product()
        if product:
            return next(
                (t for t in product["indicator"]["thermostats"] if t["ThermostatId"] == self.thermostat_id), None
            )
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update attributes based on coordinator data."""
        thermostat = self._get_thermostat()
        product = self._get_product()

        if not thermostat or not product.get("isConnected"):
            self._attr_current_temperature = None
            return

        self._attr_target_temperature = thermostat["TemperatureSet"]
        self._attr_current_temperature = thermostat["CurrentTemperature"]

        air_mode = product["indicator"]["current_air_mode"]
        self._attr_hvac_mode = self._determine_hvac_mode(air_mode)
        self._attr_hvac_action = self._determine_hvac_action(air_mode)

        if air_mode in [ALDESMode.HEAT_ECO, ALDESMode.COOL_BOOST]:
            self._attr_preset_mode = PRESET_BOOST if air_mode == ALDESMode.COOL_BOOST else PRESET_ECO
        else:
            self._attr_preset_mode = PRESET_COMFORT

    def _determine_hvac_mode(self, air_mode: ALDESMode) -> HVACMode:
        """Determine HVAC mode from air mode."""
        return {
            ALDESMode.OFF: HVACMode.OFF,
            ALDESMode.HEAT_COMFORT: HVACMode.HEAT,
            ALDESMode.HEAT_ECO: HVACMode.HEAT,
            ALDESMode.COOL_COMFORT: HVACMode.COOL,
            ALDESMode.COOL_BOOST: HVACMode.COOL,
        }.get(air_mode, HVACMode.AUTO)

    def _determine_hvac_action(self, air_mode: ALDESMode) -> HVACAction:
        """Determine HVAC action."""
        if air_mode in [ALDESMode.HEAT_COMFORT, ALDESMode.HEAT_ECO]:
            return (
                HVACAction.HEATING
                if self._attr_current_temperature < self._attr_target_temperature
                else HVACAction.IDLE
            )
        elif air_mode in [ALDESMode.COOL_COMFORT, ALDESMode.COOL_BOOST]:
            return (
                HVACAction.COOLING
                if self._attr_current_temperature > self._attr_target_temperature
                else HVACAction.IDLE
            )
        return HVACAction.OFF

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if self._attr_preset_mode == PRESET_ECO:
            target_temperature += TEMPERATURE_REDUCE_ECO

        await self.coordinator.api.set_target_temperature(
            self.modem, self.thermostat_id, self._thermostat_name, target_temperature
        )
        self._attr_target_temperature = kwargs.get(ATTR_TEMPERATURE)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        modes_map = {
            HVACMode.OFF: ALDESMode.OFF,
            HVACMode.HEAT: ALDESMode.HEAT_COMFORT,
            HVACMode.COOL: ALDESMode.COOL_COMFORT,
        }
        mode = modes_map.get(hvac_mode)
        if mode:
            await self.coordinator.api.change_mode(self.modem, mode.value, 0)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        mode_map = {
            PRESET_ECO: ALDESMode.HEAT_ECO if self._attr_hvac_mode == HVACMode.HEAT else None,
            PRESET_BOOST: ALDESMode.COOL_BOOST if self._attr_hvac_mode == HVACMode.COOL else None,
            PRESET_COMFORT: (
                ALDESMode.HEAT_COMFORT
                if self._attr_hvac_mode == HVACMode.HEAT
                else ALDESMode.COOL_COMFORT
            ),
        }
        mode = mode_map.get(preset_mode)
        if mode:
            await self.coordinator.api.change_mode(self.modem, mode.value, 0)
