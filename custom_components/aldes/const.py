"""Constants for aldes."""

from enum import StrEnum

from homeassistant.const import Platform

NAME = "Aldes"
DOMAIN = "aldes"
VERSION = "0.0.1"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

MANUFACTURER = "Aldes"
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
]

FRIENDLY_NAMES = {"TONE_AIR": "T.One® AIR", "TONE_AQUA_AIR": "T.One® AquaAIR"}


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
