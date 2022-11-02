"""Constants for aldes."""
from homeassistant.const import Platform

NAME = "Aldes"
DOMAIN = "aldes"
VERSION = "0.0.1"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

MANUFACTURER = "Aldes"
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.CLIMATE]

FRIENDLY_NAMES = {"TONE_AIR": "T.One® AIR"}
