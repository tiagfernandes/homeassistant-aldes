"""AldesEntity class."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aldes.const import (
    VERIFY_STATE_CHANGE_DELAY,
    VERIFY_STATE_CHANGE_REFRESH_DELAY,
    AirMode,
    HouseholdComposition,
    WaterMode,
)
from custom_components.aldes.coordinator import AldesDataUpdateCoordinator
from custom_components.aldes.models import DataApiEntity

_LOGGER = logging.getLogger(__name__)


class SettingsApiEntity:
    """Settings Api Entity."""

    people: HouseholdComposition | None
    antilegio: int | None
    kwh_creuse: float | None
    kwh_pleine: float | None

    def __init__(self, data: dict[str, Any] | None) -> None:
        """Initialize."""
        self.people = data.get("people") if data else None
        self.antilegio = data.get("antilegio") if data else None
        self.kwh_creuse = data.get("kwh_creuse") if data else None
        self.kwh_pleine = data.get("kwh_pleine") if data else None


class IndicatorApiEntity:
    """Thermistat Api Entity."""

    # Heat temperatur min
    fmist: int
    # Heat temperatur max
    fmast: int
    # Cool temperatur min
    cmast: int
    # Cool temperatur max
    cmist: int
    # Hot water quantity in %
    hot_water_quantity: int
    # Main temperature in °C
    main_temperature: float
    # Current air mode, default A = OFF
    current_air_mode: AirMode = AirMode.OFF
    # Current water mode, default L = OFF
    current_water_mode: WaterMode = WaterMode.OFF

    settings: SettingsApiEntity

    def __init__(self, data: dict[str, Any] | None) -> None:
        """Initialize."""
        self.fmist = data.get("fmist", 0) if data else 0
        self.fmast = data.get("fmast", 0) if data else 0
        self.cmast = data.get("cmast", 0) if data else 0
        self.cmist = data.get("cmist", 0) if data else 0
        self.hot_water_quantity = data.get("qte_eau_chaude", 0) if data else 0
        self.main_temperature = data.get("tmp_principal", 0) if data else 0
        self.current_air_mode = data.get("current_air_mode") if data else AirMode.OFF
        self.current_water_mode = (
            data.get("current_water_mode") if data else WaterMode.OFF
        )
        self.settings = SettingsApiEntity(data.get("settings") if data else None)

        if data and data.get("thermostats"):
            # Thermostats
            self.thermostats: list[ThermostatApiEntity] = [
                ThermostatApiEntity(t) for t in data["thermostats"]
            ]
        else:
            self.thermostats = []


class ThermostatApiEntity:
    """Thermistat Api Entity."""

    id: int
    name: str
    number: int
    temperature_set: int
    current_temperature: float

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize."""
        self.id = data["ThermostatId"]
        self.name = data["Name"]
        self.number = data["Number"]
        self.temperature_set = data["TemperatureSet"]
        self.current_temperature = data["CurrentTemperature"]


class DataApiEntity:
    """Data API Entity."""

    indicator: IndicatorApiEntity
    last_updated_date: str
    modem: str
    reference: str
    serial_number: str
    type: str
    filter_wear: bool
    date_last_filter_update: str
    has_filter: bool
    is_connected: bool
    week_planning: list[dict[str, str]]
    week_planning2: list[dict[str, str]]
    week_planning3: list[dict[str, str]]
    week_planning4: list[dict[str, str]]
    holidays_start: str | None
    holidays_end: str | None
    hors_gel: bool

    def __init__(self, data: dict[str, Any] | None) -> None:
        """Initialize."""
        self.indicator = IndicatorApiEntity(data.get("indicator") if data else None)
        self.last_updated_date = data.get("lastUpdatedDate", "") if data else ""
        self.modem = data.get("modem", "") if data else ""
        self.reference = data.get("reference", "") if data else ""
        self.serial_number = data.get("serial_number", "") if data else ""
        self.type = data.get("type", "") if data else ""
        self.filter_wear = data.get("usureFiltre", False) if data else False
        self.date_last_filter_update = (
            data.get("dateLastFilterUpdate", "") if data else ""
        )
        self.has_filter = data.get("hasFilter", False) if data else False
        self.is_connected = data.get("isConnected", False) if data else False
        self.week_planning = data.get("week_planning", []) if data else []
        self.week_planning2 = data.get("week_planning2", []) if data else []
        self.week_planning3 = data.get("week_planning3", []) if data else []
        self.week_planning4 = data.get("week_planning4", []) if data else []

        # Parse holidays dates and frost protection from indicator if available
        self.holidays_start = None
        self.holidays_end = None
        self.hors_gel = False
        if data and "indicator" in data and data["indicator"]:
            indicator_data = data["indicator"]
            self.holidays_start = indicator_data.get("date_debut_vac")
            self.holidays_end = indicator_data.get("date_fin_vac")
            self.hors_gel = indicator_data.get("hors_gel", False)

        _LOGGER.debug(
            "DataApiEntity initialized - Device: %s (%s), Connected: %s, "
            "Plannings loaded: week_planning=%d, week_planning2=%d, "
            "week_planning3=%d, week_planning4=%d",
            self.reference,
            self.type,
            self.is_connected,
            len(self.week_planning),
            len(self.week_planning2),
            len(self.week_planning3),
            len(self.week_planning4),
        )


@dataclass(frozen=True)
class DeviceContext:
    """Context for a specific Aldes device."""

    device_key: str
    device: DataApiEntity
    config_entry: ConfigEntry


class AldesEntity(CoordinatorEntity):
    """Aldes entity."""

    coordinator: AldesDataUpdateCoordinator
    _device_key: str
    serial_number: str
    reference: str
    modem: str
    is_connected: bool

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        context: DeviceContext,
    ) -> None:
        """Initialize the AldesEntity."""
        super().__init__(coordinator)
        self._attr_config_entry = context.config_entry
        self._device_key = context.device_key
        self.serial_number = context.device.serial_number
        self.reference = context.device.reference
        self.modem = context.device.modem
        self.is_connected = context.device.is_connected

    @property
    def device_identifier(self) -> str:
        """
        Return a stable identifier for the device.

        Preference order: `serial_number` (if present and not 'N/A'), then `modem`,
        then internal `_device_key` as a last resort.
        """
        # Preference: serial (to preserve existing entity IDs) -> modem -> device_key
        try:
            serial = (self.serial_number or "").strip()
        except (AttributeError, TypeError):
            serial = ""
        if serial and serial.upper() != "N/A":
            return serial

        try:
            modem = (self.modem or "").strip()
        except (AttributeError, TypeError):
            modem = ""
        if modem:
            return modem

        return str(self._device_key)

    def _get_device(self) -> DataApiEntity | None:
        """Return current device data from the coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._device_key)

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self._friendly_name_internal()

    def _friendly_name_internal(self) -> str | None:
        """Return the friendly name - to be overridden by subclasses."""
        return None

    async def _verify_state_change_after_delay(  # noqa: PLR0913
        self,
        get_current_fn: Callable[[], Any],
        expected_value: Any,
        retry_fn: Callable[[], Awaitable[None]],
        threshold: float = 0,
        command_name: str = "change",
        max_retries: int = 1,
    ) -> None:
        """
        Verify a state change was applied after a delay and retry if needed.

        Generic method for verifying that any state change (temperature, mode, etc.)
        was actually applied by the API, and retry if not.

        Args:
            get_current_fn: Callable that returns the current value from device data
            expected_value: The value we expect to have after the command
            retry_fn: Async callable to retry the command if not applied
            threshold: Maximum allowed difference for numeric values (default 0)
            command_name: Name of the command for logging (default "change")
            max_retries: Maximum number of retry attempts (default 1)

        """
        try:
            for attempt in range(1, max_retries + 1):
                await asyncio.sleep(VERIFY_STATE_CHANGE_DELAY)

                # Force a coordinator refresh to get latest data
                await self.coordinator.async_request_refresh()
                await asyncio.sleep(VERIFY_STATE_CHANGE_REFRESH_DELAY)

                # Get current value
                current_value = get_current_fn()

                # Check if the state was actually updated
                is_changed = (
                    abs(current_value - expected_value) <= threshold
                    if isinstance(expected_value, int | float)
                    else current_value == expected_value
                )

                if is_changed:
                    _LOGGER.debug(
                        "%s successfully updated to %s (attempt %d/%d)",
                        command_name.title(),
                        expected_value,
                        attempt,
                        max_retries,
                    )
                    break

                # Not changed - log attempt and retry if we have attempts remaining
                if attempt < max_retries:
                    _LOGGER.warning(
                        "%s not updated after %d seconds (attempt %d/%d, "
                        "expected: %s, actual: %s). Retrying...",
                        command_name.title(),
                        VERIFY_STATE_CHANGE_DELAY,
                        attempt,
                        max_retries,
                        expected_value,
                        current_value,
                    )
                    # Retry the command
                    await retry_fn()
                else:
                    _LOGGER.warning(
                        "%s not updated after %d seconds (final attempt %d/%d, "
                        "expected: %s, actual: %s)",
                        command_name.title(),
                        VERIFY_STATE_CHANGE_DELAY,
                        attempt,
                        max_retries,
                        expected_value,
                        current_value,
                    )

        except asyncio.CancelledError:
            _LOGGER.debug("%s verification cancelled", command_name.title())
        except Exception:
            _LOGGER.exception("Error verifying %s", command_name)
