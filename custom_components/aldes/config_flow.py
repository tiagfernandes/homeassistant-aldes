"""Adds config flow for Aldes."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AldesApi, AuthenticationError
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)


class AldesFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Aldes."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle a flow initialized by the user."""
        self._errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            valid = await self._test_credentials(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if valid:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
            self._errors["base"] = "auth"
            return await self._show_config_form(user_input)

        user_input = {}
        # Provide defaults for form
        user_input[CONF_USERNAME] = ""
        user_input[CONF_PASSWORD] = ""

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input: dict[str, str]) -> Any:
        """Show the configuration form to edit location data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=user_input[CONF_USERNAME]): str,  # type: ignore  # noqa: PGH003
                    vol.Required(CONF_PASSWORD, default=user_input[CONF_PASSWORD]): str,  # type: ignore  # noqa: PGH003
                }
            ),
            errors=self._errors,
        )

    async def _test_credentials(self, username: str, password: str) -> bool:
        """Return true if credentials is valid."""
        try:
            session = async_create_clientsession(self.hass)
            api = AldesApi(username, password, session)
            await api.authenticate()
        except AuthenticationError:
            return False
        else:
            return True
