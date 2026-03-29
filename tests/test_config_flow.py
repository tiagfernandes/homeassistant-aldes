"""Test the Aldes config flow."""

from unittest.mock import patch

import pytest

from custom_components.aldes.api import AuthenticationError
from custom_components.aldes.const import DOMAIN


@pytest.mark.skip(reason="Requires Home Assistant test context")
async def test_form(hass):
    """Test we get the form."""
    from homeassistant import config_entries
    from homeassistant.data_entry_flow import FlowResultType

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}

    with patch(
        "custom_components.aldes.config_flow.AldesApi.authenticate",
        return_value=True,
    ), patch(
        "custom_components.aldes.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "username": "test-username",
                "password": "test-password",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "test-username"
    assert result2["data"] == {
        "username": "test-username",
        "password": "test-password",
    }
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.skip(reason="Requires Home Assistant test context")
async def test_form_invalid_auth(hass):
    """Test we handle invalid auth."""
    from homeassistant import config_entries
    from homeassistant.data_entry_flow import FlowResultType

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.aldes.config_flow.AldesApi.authenticate",
        side_effect=AuthenticationError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "username": "test-username",
                "password": "test-password",
            },
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "auth"}
