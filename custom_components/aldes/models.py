"""Models for Aldes integration."""

import logging
from enum import IntEnum, StrEnum
from typing import Any

_LOGGER = logging.getLogger(__name__)


class ApiHealthState(StrEnum):
    """API Health states."""

    ONLINE = "online"
    RETRYING = "retrying"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class CommandUid(IntEnum):
    """Command UIDs for API requests."""

    AIR_MODE = 1
    HOT_WATER = 2


class AirMode(StrEnum):
    """Aldes Air Mode."""

    OFF = "A"
    HEAT_COMFORT = "B"
    HEAT_ECO = "C"
    HEAT_PROG_A = "D"
    HEAT_PROG_B = "E"
    COOL_COMFORT = "F"
    COOL_BOOST = "G"
    COOL_PROG_A = "H"
    COOL_PROG_B = "I"


class WaterMode(StrEnum):
    """Aldes Water Mode."""

    OFF = "L"
    ON = "M"
    BOOST = "N"


class HouseholdComposition(StrEnum):
    """Household composition for Hot water."""

    TWO = "0"
    THREE = "1"
    FOUR = "2"
    FIVE = "3"
    FIVE_AND_MORE = "4"


class AntilegionellaCycle(StrEnum):
    """Household composition for Hot water."""

    OFF = "0"
    MONDAY = "1"
    TUESDAY = "2"
    WEDNESDAY = "3"
    THURSDAY = "4"
    FRIDAY = "5"
    SATURDAY = "6"
    SUNDAY = "7"


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
    thermostats: list[ThermostatApiEntity]

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
        self.thermostats = []

        if data and data.get("thermostats"):
            self.thermostats = [
                ThermostatApiEntity(t) for t in data["thermostats"]
            ]


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
