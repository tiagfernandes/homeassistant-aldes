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

    from custom_components.aldes.models import DataApiEntity

    from .api import AldesApi

_LOGGER = logging.getLogger(__name__)


class AldesDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Aldes data coordinator."""

    _API_TIMEOUT = 10
    skip_next_update: bool = False
    data: dict[str, DataApiEntity]

    def __init__(self, hass: HomeAssistant, api: AldesApi) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, DataApiEntity]:
        """Update data via library."""
        if self.skip_next_update:
            self.skip_next_update = False
            # Return existing data instead of None to avoid losing state
            return self.data if hasattr(self, "data") and self.data else {}
        try:
            async with async_timeout.timeout(self._API_TIMEOUT):
                data = await self.api.fetch_data()
                # If we got no data, keep existing data
                if not data and hasattr(self, "data") and self.data:
                    _LOGGER.warning(
                        "Received empty data from API, keeping existing data"
                    )
                    return self.data
                return data or {}
        except Exception as exception:
            # On error, keep existing data if available
            if hasattr(self, "data") and self.data:
                _LOGGER.exception("Error updating data, keeping existing")
                return self.data
            raise UpdateFailed(exception) from exception
        finally:
            # After every update, check if pending commands were applied
            await self._verify_pending_commands()

    async def _verify_pending_commands(self) -> None:
        """Check pending commands and retry if not applied."""
        pending = self.api.get_pending_verifications(timeout_seconds=60)
        if not pending:
            return

        _LOGGER.debug("Checking %d pending command(s)", len(pending))

        for verification_id, metadata in pending.items():
            try:
                # Get the retry function if available
                retry_fn = metadata.get("retry_fn")
                if not retry_fn:
                    _LOGGER.debug(
                        "No retry function for pending command %s",
                        verification_id,
                    )
                    self.api.unregister_pending_verification(verification_id)
                    continue

                # Call the verification check (e.g., did temp change?)
                is_applied = metadata.get("is_applied_fn", lambda: True)()
                if is_applied:
                    _LOGGER.debug(
                        "Pending command %s was applied successfully",
                        verification_id,
                    )
                    self.api.unregister_pending_verification(verification_id)
                else:
                    _LOGGER.warning(
                        "Pending command %s was NOT applied, retrying...",
                        verification_id,
                    )
                    # Retry the command
                    try:
                        await retry_fn()
                    except Exception:
                        _LOGGER.exception(
                            "Failed to retry pending command %s",
                            verification_id,
                        )
                    # Note: We don't unregister yet - will check again next time
            except Exception:
                _LOGGER.exception(
                    "Error verifying pending command %s",
                    verification_id,
                )
