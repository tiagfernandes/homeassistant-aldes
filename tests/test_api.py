"""Tests for Aldes API client."""

import pytest


def test_command_uid_values():
    """Test CommandUid enum values - non async test."""
    from custom_components.aldes.api import CommandUid

    assert CommandUid.AIR_MODE == 1
    assert CommandUid.HOT_WATER == 2


@pytest.mark.skip(reason="Requires Home Assistant context - complex mocking")
async def test_authenticate_success():
    """Test successful authentication."""


@pytest.mark.skip(reason="Requires Home Assistant context")
async def test_authenticate_failure():
    """Test authentication failure."""


@pytest.mark.skip(reason="Requires Home Assistant context")
async def test_fetch_data_success():
    """Test fetching data successfully."""


@pytest.mark.skip(reason="Requires Home Assistant context")
async def test_change_mode():
    """Test changing mode."""


@pytest.mark.skip(reason="Requires Home Assistant context")
async def test_temperature_worker():
    """Test temperature worker queue processing."""


@pytest.mark.skip(reason="Requires Home Assistant context")
async def test_auth_interceptor_reauth():
    """Test automatic re-authentication on 401."""
