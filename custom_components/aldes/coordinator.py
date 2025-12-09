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
            # Return existing data instead of None to avoid losing state
            return self.data if hasattr(self, "data") and self.data else None
        try:
            async with async_timeout.timeout(self._API_TIMEOUT):
                data = await self.api.fetch_data()
                # If we got None or invalid data, keep existing data
                if data is None and hasattr(self, "data") and self.data:
                    _LOGGER.warning("Received None from API, keeping existing data")
                    return self.data
                return data
        except Exception as exception:
            # On error, keep existing data if available
            if hasattr(self, "data") and self.data:
                _LOGGER.error("Error updating data, keeping existing: %s", exception)
                return self.data
            raise UpdateFailed(exception) from exception
