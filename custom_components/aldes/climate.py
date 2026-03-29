"""Support for the Aldes sensors."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
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
from homeassistant.util import dt as dt_util

from custom_components.aldes.const import (
    DOMAIN,
    ECO_MODE_TEMPERATURE_OFFSET,
    HOUR_TO_CHAR_THRESHOLD,
    MANUFACTURER,
    PROGRAM_COMFORT,
    PROGRAM_ECO,
    PROGRAM_OFF,
    SLOT_MIN_LENGTH,
    TEMPERATURE_VERIFY_THRESHOLD,
    AirMode,
)
from custom_components.aldes.entity import (
    AldesEntity,
    DeviceContext,
    ThermostatApiEntity,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add Aldes sensors from a config entry."""
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
        sensors.extend(
            [
                AldesClimateEntity(
                    coordinator,
                    context,
                    thermostat,
                )
                for thermostat in device.indicator.thermostats
            ]
        )

    async_add_entities(sensors)


class AldesClimateEntity(AldesEntity, ClimateEntity):
    """Define an Aldes climate entity."""

    coordinator: AldesDataUpdateCoordinator

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
        thermostat: ThermostatApiEntity,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            context,
        )
        self.thermostat = thermostat
        self._attr_unique_id = f"{self.thermostat.id}_{self.thermostat.name}_climate"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        self._attr_target_temperature_step = 1.0
        self._attr_precision = 1.0
        self._attr_hvac_action = HVACAction.OFF
        # Store effective mode for use in temperature calculations
        self._effective_air_mode: AirMode | None = None
        self._retry_task: asyncio.Task | None = None
        self._retry_mode_task: asyncio.Task | None = None
        
        # Optimistic state management
        self._optimistic_target_temp: float | None = None
        self._optimistic_hvac_mode: HVACMode | None = None
        self._optimistic_end_time: datetime | None = None
        
        # Track pending changes
        self._pending_temperature_change: dict[str, Any] | None = None
        self._pending_mode_change: dict[str, Any] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        identifier = str(self.thermostat.id)
        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer=MANUFACTURER,
            name=f"Thermostat {self.thermostat.id!s} {self.thermostat.name}",
            via_device=(DOMAIN, self.device_identifier),
        )

    def _friendly_name_internal(self) -> str | None:
        """Return friendly name for the climate entity (thermostat)."""
        return f"Thermostat {self.thermostat.name}"

    def _get_current_time_slot(self) -> str:
        """Get current time slot character (0-9, A-N for hours 0-23)."""
        now = dt_util.now()
        # Hours: 0-9 = '0'-'9', 10-23 = 'A'-'N'
        hour = now.hour
        # For now, return just the hour character
        return (
            str(hour)
            if hour < HOUR_TO_CHAR_THRESHOLD
            else chr(ord("A") + (hour - HOUR_TO_CHAR_THRESHOLD))
        )

    def _get_current_day(self) -> int:
        """Get current day of week (0=Lundi, ..., 5=Samedi, 6=Dimanche)."""
        now = dt_util.now()
        # weekday() returns 0=Monday, 6=Sunday
        # Format Aldes: 0=Lundi, 1=Mardi, ..., 6=Dimanche
        return now.weekday()

    def _get_program_at_slot(self, planning: list[Any]) -> str | None:
        """
        Get the active program at current time and day from planning.

        Planning format: each entry is "[heure][jour][mode]"
        where heure = 0-9 or A-N (for 10-23h), jour = 0-6, mode = B/C/0
        Example: "K6B" means 20h (K=20), dimanche (6), Confort (B)
        """
        if not planning or len(planning) == 0:
            return None

        current_hour_char = self._get_current_time_slot()
        current_day = self._get_current_day()
        current_day_str = str(current_day)

        # Search for matching slot in planning
        for item in planning:
            slot_str = None
            if isinstance(item, dict):
                slot_str = item.get("command")
            elif isinstance(item, str):
                slot_str = item

            if slot_str and len(slot_str) >= SLOT_MIN_LENGTH:
                # Format: "XYZ" where X=hour char, Y=day digit, Z=mode
                hour_char = slot_str[0]
                day_char = slot_str[1]

                if hour_char == current_hour_char and day_char == current_day_str:
                    return slot_str

        return None

    def _get_heating_program_char(self, slot_data: str) -> str | None:
        """
        Extract heating program character from planning slot data.

        Format: [heure][jour][mode].
        """
        if not slot_data or len(slot_data) < SLOT_MIN_LENGTH:
            return None
        # Le mode est le dernier caractère
        return slot_data[-1]

    def _get_cooling_program_char(self, slot_data: str) -> str | None:
        """
        Extract cooling program character from planning slot data.

        Format: [heure][jour][mode].
        """
        if not slot_data or len(slot_data) < SLOT_MIN_LENGTH:
            return None
        # Le mode est aussi le dernier caractère
        return slot_data[-1]

    def _get_active_program_mode(self, air_mode: AirMode) -> AirMode | None:
        """
        Get the effective HVAC mode considering the active program.

        If in program mode (HEAT_PROG_A, HEAT_PROG_B, COOL_PROG_A, COOL_PROG_B),
        adjust the mode based on what program is active in the planning.
        """
        device = self._get_device()
        if not device:
            return None
        _LOGGER.debug("Calculating active program mode for air_mode: %s", air_mode)
        # Check if we're in a program mode
        is_heating_prog_a = air_mode == AirMode.HEAT_PROG_A
        is_heating_prog_b = air_mode == AirMode.HEAT_PROG_B
        is_cooling_prog_a = air_mode == AirMode.COOL_PROG_A
        is_cooling_prog_b = air_mode == AirMode.COOL_PROG_B

        # Determine heating/cooling and get planning data
        if is_heating_prog_a or is_heating_prog_b:
            planning_key = "week_planning" if is_heating_prog_a else "week_planning2"
            planning = getattr(device, planning_key, [])
            slot_data = self._get_program_at_slot(planning)
            program_char = (
                self._get_heating_program_char(slot_data) if slot_data else None
            )

            _LOGGER.debug(
                "Heating program mode: air_mode=%s, planning_key=%s, slot_data=%s, "
                "program_char=%s",
                air_mode,
                planning_key,
                slot_data,
                program_char,
            )

            # Map heating program character to effective air mode
            heating_modes = {
                PROGRAM_OFF: AirMode.OFF,
                PROGRAM_COMFORT: AirMode.HEAT_COMFORT,
                PROGRAM_ECO: AirMode.HEAT_ECO,
            }
            result = heating_modes.get(program_char) if program_char else None
            _LOGGER.debug("Heating mode result: %s", result)
            return result

        if is_cooling_prog_a or is_cooling_prog_b:
            planning_key = "week_planning3" if is_cooling_prog_a else "week_planning4"
            planning = getattr(device, planning_key, [])
            slot_data = self._get_program_at_slot(planning)
            program_char = (
                self._get_cooling_program_char(slot_data) if slot_data else None
            )

            _LOGGER.debug(
                "Cooling program mode: air_mode=%s, planning_key=%s, slot_data=%s, "
                "program_char=%s",
                air_mode,
                planning_key,
                slot_data,
                program_char,
            )

            # Map cooling program character to effective air mode
            # Cooling planning only uses: 0=Off, B=Comfort (no Eco mode)
            cooling_modes = {
                PROGRAM_OFF: AirMode.OFF,
                PROGRAM_COMFORT: AirMode.COOL_COMFORT,
            }
            result = cooling_modes.get(program_char) if program_char else None
            _LOGGER.debug("Cooling mode result: %s", result)
            return result

        return None

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
        device = self._get_device()
        if device is None or device.indicator is None:
            return None

        # Use the effective mode that was calculated in _async_update_attrs
        effective_mode = self._effective_air_mode

        # Fallback: if not yet set, calculate it now
        if effective_mode is None:
            air_mode = device.indicator.current_air_mode
            effective_mode = self._get_active_program_mode(air_mode) or air_mode

        # Determine if heating based on effective mode
        is_heating_mode = effective_mode not in [
            AirMode.COOL_COMFORT,
            AirMode.COOL_BOOST,
            AirMode.OFF,
        ]

        temp_key_map = {
            "min": ("cmist", "fmist"),  # (heating, cooling)
            "max": ("cmast", "fmast"),
        }
        heating_key, cooling_key = temp_key_map.get(temp_type, ("cmist", "fmist"))
        temp_key = heating_key if is_heating_mode else cooling_key

        temperature = getattr(device.indicator, temp_key, None)

        # Apply ECO mode offset for heating modes
        if temperature is not None and effective_mode == AirMode.HEAT_ECO:
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
        device = self._get_device()
        if device is None or device.indicator is None:
            self._attr_current_temperature = None
            return

        thermostat = self._get_thermostat_by_id(device, self.thermostat.id)

        if not thermostat or not device.is_connected:
            self._attr_current_temperature = None
            return

        self._attr_current_temperature = thermostat.current_temperature

        air_mode = device.indicator.current_air_mode

        # Get the effective mode considering active program
        self._effective_air_mode = self._get_active_program_mode(air_mode) or air_mode

        self._attr_hvac_mode = self._determine_hvac_mode(self._effective_air_mode)

        # ECO mode displays temperature offset for user clarity
        temperature_offset = (
            ECO_MODE_TEMPERATURE_OFFSET
            if self._effective_air_mode == AirMode.HEAT_ECO
            else 0
        )
        self._attr_target_temperature = thermostat.temperature_set - temperature_offset

        # Determine action AFTER target_temperature is set
        self._attr_hvac_action = self._determine_hvac_action(self._effective_air_mode)

    def _get_thermostat_by_id(
        self, device: Any, target_id: int
    ) -> ThermostatApiEntity | None:
        """Return thermostat object by id."""
        if device is None or device.indicator is None:
            return None

        return next(
            (
                thermostat
                for thermostat in device.indicator.thermostats
                if thermostat.id == target_id
            ),
            None,
        )

    def _determine_hvac_mode(self, air_mode: AirMode) -> HVACMode:
        """
        Determine HVAC mode from air mode.

        For program modes, the display adapts based on active program.
        """
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
        """
        Determine HVAC action based on current vs target temperature.

        This accounts for the effective Eco mode value.
        """
        if air_mode == AirMode.OFF:
            return HVACAction.OFF

        if (
            self._attr_current_temperature is None
            or self._attr_target_temperature is None
        ):
            return HVACAction.OFF

        current_temperature = self._attr_current_temperature

        # Utilise la consigne réelle (celle affichée à l'utilisateur)
        target_temperature = self._attr_target_temperature

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
        """Set new target temperature sans double offset Eco."""
        target_temperature = kwargs.get(ATTR_TEMPERATURE)
        if target_temperature is None:
            return

        device = self._get_device()
        if device is None or device.indicator is None:
            return
        air_mode = device.indicator.current_air_mode

        # On ne rajoute l'offset Eco que si on n'est PAS déjà en mode Eco effectif
        effective_mode = self._effective_air_mode or air_mode
        if effective_mode == AirMode.HEAT_ECO:
            pac_target = int(target_temperature + ECO_MODE_TEMPERATURE_OFFSET)
        else:
            pac_target = int(target_temperature)

        await self.coordinator.api.set_target_temperature(
            self.modem, self.thermostat.id, self.thermostat.name, pac_target
        )

        # --- ENABLE OPTIMISTIC STATE ---
        self._optimistic_target_temp = target_temperature
        self._optimistic_end_time = dt_util.now() + timedelta(
            seconds=OPTIMISTIC_HOLD_DURATION
        )

        # Update internal state immediately
        self._attr_target_temperature = target_temperature
        self._attr_hvac_action = self._determine_hvac_action(effective_mode)
        self.async_write_ha_state()

        # Cancel any existing retry task
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()

        # Store the pending change for retry verification
        expected_target = pac_target

        # Create getter and retry functions for generic verification
        def get_current_temperature() -> int:
            """Get current target temperature from device."""
            device = self._get_device()
            if device is None or device.indicator is None:
                return 0
            for thermostat in device.indicator.thermostats:
                if thermostat.id == self.thermostat.id:
                    return thermostat.temperature_set
            return 0

        async def retry_temperature() -> None:
            """Retry setting the temperature."""
            await self.coordinator.api.set_target_temperature(
                self.modem, self.thermostat.id, self.thermostat.name, expected_target
            )

        # Schedule verification
        self._retry_task = asyncio.create_task(
            self._verify_state_change_after_delay(
                get_current_fn=get_current_temperature,
                expected_value=expected_target,
                retry_fn=retry_temperature,
                threshold=TEMPERATURE_VERIFY_THRESHOLD,
                command_name="temperature",
                max_retries=3,
            )
        )

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

        # --- ENABLE OPTIMISTIC STATE ---
        self._optimistic_hvac_mode = hvac_mode
        self._optimistic_end_time = dt_util.now() + timedelta(
            seconds=OPTIMISTIC_HOLD_DURATION
        )

        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

        # Cancel any existing retry task
        if self._retry_mode_task and not self._retry_mode_task.done():
            self._retry_mode_task.cancel()

        # Store expected mode for verification
        expected_air_mode = air_mode

        # Create getter and retry functions for generic verification
        def get_current_mode() -> AirMode:
            """Get current air mode from device."""
            device = self._get_device()
            if device is None or device.indicator is None:
                return AirMode.OFF
            return device.indicator.current_air_mode

        async def retry_mode() -> None:
            """Retry changing the mode."""
            await self.coordinator.api.change_mode(
                self.modem, expected_air_mode.value, CommandUid.AIR_MODE
            )

        # Schedule verification
        self._retry_mode_task = asyncio.create_task(
            self._verify_state_change_after_delay(
                get_current_fn=get_current_mode,
                expected_value=expected_air_mode,
                retry_fn=retry_mode,
                threshold=0,
                command_name="air mode",
                max_retries=3,
            )
        )

    async def async_turn_on(self) -> None:
        """Turn on the climate device."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn off the climate device."""
        await self.async_set_hvac_mode(HVACMode.OFF)
