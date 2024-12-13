"""Aldes."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import async_timeout
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from custom_components.aldes.entity import DataApiEntity

    from .api import AldesApi

_LOGGER = logging.getLogger(__name__)


class AldesDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Aldes data coordinator."""

    _API_TIMEOUT = 10
    skip_next_update: bool = False
    data: DataApiEntity

    def __init__(self, hass: HomeAssistant, api: AldesApi) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )
        self.api = api

    async def _async_update_data(self) -> DataApiEntity | None:
        """Update data via library."""
        if self.skip_next_update:
            self.skip_next_update = False
            return
        try:
            async with async_timeout.timeout(self._API_TIMEOUT):
                return await self.api.fetch_data()
        except Exception as exception:
            raise UpdateFailed(exception) from exception
