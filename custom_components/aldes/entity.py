"""AldesEntity class."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aldes.const import AirMode, HouseholdComposition, WaterMode
from custom_components.aldes.coordinator import AldesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class SettingsApiEntity:
    """Settings Api Entity."""

    people: HouseholdComposition | None
    antilegio: int | None

    def __init__(self, data: dict[str, Any] | None) -> None:
        """Initialize."""
        self.people = data["people"] if data else None
        self.antilegio = data["antilegio"] if data else None


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
        self.fmist = data["fmist"] if data else 0
        self.fmast = data["fmast"] if data else 0
        self.cmast = data["cmast"] if data else 0
        self.cmist = data["cmist"] if data else 0
        self.hot_water_quantity: int = data["qte_eau_chaude"] if data else 0
        self.main_temperature: float = data["tmp_principal"] if data else 0
        self.current_air_mode = data["current_air_mode"] if data else AirMode.OFF
        self.current_water_mode = data["current_water_mode"] if data else WaterMode.OFF
        self.settings = SettingsApiEntity(data["settings"] if data else None)

        if data:
            # Thermostats
            self.thermostats: list[ThermostatApiEntity] = [
                ThermostatApiEntity(t) for t in data["thermostats"]
            ]


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

    def __init__(self, data: dict[str, Any] | None) -> None:
        """Initialize."""
        self.indicator = IndicatorApiEntity(data["indicator"] if data else None)
        self.last_updated_date = data["lastUpdatedDate"] if data else ""
        self.modem = data["modem"] if data else ""
        self.reference = data["reference"] if data else ""
        self.serial_number = data["serial_number"] if data else ""
        self.type = data["type"] if data else ""
        self.filter_wear = data["usureFiltre"] if data else False
        self.date_last_filter_update = data["dateLastFilterUpdate"] if data else ""
        self.has_filter = data["hasFilter"] if data else False
        self.is_connected = data["isConnected"] if data else False
        self.week_planning = data["week_planning"] if data else []
        self.week_planning2 = data["week_planning2"] if data else []
        self.week_planning3 = data["week_planning3"] if data else []
        self.week_planning4 = data["week_planning4"] if data else []

        _LOGGER.info(
            "DataApiEntity initialized - Device: %s (%s), Serial: %s, Connected: %s, "
            "Plannings loaded: week_planning=%d, week_planning2=%d, week_planning3=%d, week_planning4=%d",
            self.reference,
            self.type,
            self.serial_number,
            self.is_connected,
            len(self.week_planning),
            len(self.week_planning2),
            len(self.week_planning3),
            len(self.week_planning4),
        )


class AldesEntity(CoordinatorEntity):
    """Aldes entity."""

    coordinator: AldesDataUpdateCoordinator
    serial_number: str
    reference: str
    modem: str
    is_connected: bool

    def __init__(
        self,
        coordinator: AldesDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the AldesEntity."""
        super().__init__(coordinator)
        self._attr_config_entry = config_entry
        self.serial_number = coordinator.data.serial_number
        self.reference = coordinator.data.reference
        self.modem = coordinator.data.modem
        self.is_connected = coordinator.data.is_connected
