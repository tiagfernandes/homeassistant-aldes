"""Constants for aldes."""

from enum import StrEnum

from homeassistant.const import Platform

NAME = "Aldes"
DOMAIN = "aldes"
VERSION = "0.0.1"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"  # noqa: S105

MANUFACTURER = "Aldes"
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

FRIENDLY_NAMES = {"TONE_AIR": "T.One® AIR", "TONE_AQUA_AIR": "T.One® AquaAIR"}

# ECO mode temperature offset (displayed to user as -2°C, sent to API as +2°C)
ECO_MODE_TEMPERATURE_OFFSET = 2


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
