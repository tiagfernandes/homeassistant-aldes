"""Pytest configuration for Aldes tests."""

import sys
from unittest.mock import MagicMock

# Create a proper mock module that acts as a package
homeassistant_mock = MagicMock()

# Mock all Home Assistant modules BEFORE any imports
sys.modules["homeassistant"] = homeassistant_mock
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.data_entry_flow"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.climate"] = MagicMock()
sys.modules["homeassistant.components.climate.const"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.components.sensor.const"] = MagicMock()
sys.modules["homeassistant.components.number"] = MagicMock()
sys.modules["homeassistant.components.select"] = MagicMock()
sys.modules["homeassistant.components.binary_sensor"] = MagicMock()
sys.modules["homeassistant.components.button"] = MagicMock()
sys.modules["homeassistant.components.text"] = MagicMock()
sys.modules["homeassistant.components.http"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()
sys.modules["homeassistant.helpers.entity"] = MagicMock()
sys.modules["homeassistant.helpers.entity_platform"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["homeassistant.util.dt"] = MagicMock()

# Mock voluptuous
sys.modules["voluptuous"] = MagicMock()

# Mock aiohttp
sys.modules["aiohttp"] = MagicMock()
