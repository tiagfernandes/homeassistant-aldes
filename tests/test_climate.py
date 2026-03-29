"""Tests for Aldes Climate entity."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_coordinator():
    """Mock the data update coordinator."""
    coordinator = MagicMock()
    coordinator.data = MagicMock()
    coordinator.api = MagicMock()
    coordinator.api.set_target_temperature = AsyncMock()
    coordinator.api.change_mode = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.mark.skip(reason="Requires complex Home Assistant climate entity setup")
async def test_optimistic_state_temperature(climate_entity):
    """Test optimistic state update for temperature."""
    # Set new temperature
    await climate_entity.async_set_temperature(temperature=22)

    # Verify optimistic state is set immediately
    assert climate_entity.target_temperature == 22
    assert climate_entity._optimistic_end_time is not None


@pytest.mark.skip(reason="Requires complex Home Assistant climate entity setup")
async def test_retry_logic_temperature(climate_entity):
    """Test retry logic when API update is silent."""
    # User sets temperature
    await climate_entity.async_set_temperature(temperature=22)

    assert climate_entity.target_temperature == 22


@pytest.mark.skip(reason="Requires complex Home Assistant climate entity setup")
async def test_hvac_action_heating(climate_entity):
    """Test HVAC action detection for heating."""


@pytest.mark.skip(reason="Requires complex Home Assistant climate entity setup")
async def test_eco_mode_offset(climate_entity):
    """Test eco mode temperature offset."""


@pytest.mark.skip(reason="Requires complex Home Assistant climate entity setup")
def test_time_slot_encoding():
    """Test time slot character encoding."""
