"""AldesConnect"""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AldesConnectApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AldesConnectDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """AldesConnect data coordinator."""

    _API_TIMEOUT = 10

    def __init__(self, hass: HomeAssistant, api: AldesConnectApi):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            async with async_timeout.timeout(self._API_TIMEOUT):
                return await self.api.fetch_data()
        except Exception as exception:
            raise UpdateFailed(exception) from exception
