"""AldesEntity class."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aldes.const import AirMode, WaterMode
from custom_components.aldes.coordinator import AldesDataUpdateCoordinator


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
