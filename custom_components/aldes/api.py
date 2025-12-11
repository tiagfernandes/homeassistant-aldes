"""Aldes API client."""

import asyncio
import logging
from enum import IntEnum
from typing import Any

import aiohttp

from custom_components.aldes.entity import DataApiEntity

_LOGGER = logging.getLogger(__name__)

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
REQUEST_DELAY = 5  # Delay between queued requests in seconds


class CommandUid(IntEnum):
    """Command UIDs for API requests."""

    AIR_MODE = 1
    HOT_WATER = 2


class AldesApi:
    """Aldes API client."""

    _API_URL_TOKEN = "https://aldesiotsuite-aldeswebapi.azurewebsites.net/oauth2/token"  # noqa: S105
    _API_URL_PRODUCTS = "https://aldesiotsuite-aldeswebapi.azurewebsites.net/aldesoc/v5/users/me/products"  # pylint: disable=line-too-long
    _AUTHORIZATION_HEADER_KEY = "Authorization"
    _TOKEN_TYPE = "Bearer"  # noqa: S105

    def __init__(
        self, username: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        """Initialize Aldes API client."""
        self._username = username
        self._password = password
        self._session = session
        self._token = ""
        self.queue_target_temperature: asyncio.Queue[tuple[str, int, str, Any]] = (
            asyncio.Queue()
        )

        asyncio.create_task(self._temperature_worker())

    async def authenticate(self) -> None:
        """Authenticate and retrieve access token from Aldes API."""
        _LOGGER.info("Authenticating with Aldes API...")
        data: dict[str, str] = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
        }

        async with self._session.post(self._API_URL_TOKEN, data=data) as response:
            json = await response.json()
            if response.status == HTTP_OK:
                self._token = json["access_token"]
                _LOGGER.info("Successfully authenticated with Aldes API")
            else:
                error_msg = f"Authentication failed with status {response.status}"
                _LOGGER.error(error_msg)
                raise AuthenticationError(error_msg)

    async def change_mode(self, modem: str, mode: str, uid: CommandUid) -> Any:
        """Change mode (air or hot water)."""
        mode_type = "air" if uid == CommandUid.AIR_MODE else "hot water"
        _LOGGER.info("Changing %s mode to: %s", mode_type, mode)
        return await self._send_command(modem, "changeMode", uid, mode)

    async def fetch_data(self) -> Any:
        """Fetch data."""
        _LOGGER.debug("Fetching data from Aldes API...")
        async with await self._request_with_auth_interceptor(
            self._session.get, self._API_URL_PRODUCTS
        ) as response:
            data = await response.json()
            _LOGGER.debug("Fetched data: %s", data)

            if isinstance(data, list) and len(data) > 0:
                _LOGGER.debug("Successfully retrieved Aldes device data")
                return DataApiEntity(data[0])

            _LOGGER.warning("No data received from Aldes API")
            return None

    async def _temperature_worker(self) -> None:
        """Process temperature change requests from queue with delay between each."""
        while True:
            (
                modem,
                thermostat_id,
                thermostat_name,
                temperature,
            ) = await self.queue_target_temperature.get()
            if modem and thermostat_id and thermostat_name and temperature:
                await self.change_temperature(
                    modem, thermostat_id, thermostat_name, temperature
                )
                await asyncio.sleep(REQUEST_DELAY)
            self.queue_target_temperature.task_done()

    async def set_target_temperature(
        self,
        modem: str,
        thermostat_id: int,
        thermostat_name: str,
        target_temperature: Any,
    ) -> None:
        """Set target temperature."""
        await self.queue_target_temperature.put(
            (modem, thermostat_id, thermostat_name, target_temperature)
        )

    async def change_temperature(
        self,
        modem: str,
        thermostat_id: int,
        thermostat_name: str,
        target_temperature: Any,
    ) -> Any:
        """Change temperature of thermostat."""
        _LOGGER.info(
            "Changing temperature for thermostat %s (%s) to %s°C",
            thermostat_id,
            thermostat_name,
            target_temperature,
        )
        async with await self._request_with_auth_interceptor(
            self._session.patch,
            f"{self._API_URL_PRODUCTS}/{modem}/updateThermostats",
            json=[
                {
                    "ThermostatId": thermostat_id,
                    "Name": thermostat_name,
                    "TemperatureSet": int(target_temperature),
                }
            ],
        ) as response:
            result = await response.json()
            _LOGGER.debug("Temperature change response: %s", result)
            return result

    async def _request_with_auth_interceptor(
        self, request: Any, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Execute request with automatic re-authentication if needed."""
        initial_response = await request(
            url,
            headers={self._AUTHORIZATION_HEADER_KEY: self._build_authorization()},
            **kwargs,
        )
        if initial_response.status == HTTP_UNAUTHORIZED:
            initial_response.close()
            await self.authenticate()
            return await request(
                url,
                headers={self._AUTHORIZATION_HEADER_KEY: self._build_authorization()},
                **kwargs,
            )
        return initial_response

    def _build_authorization(self) -> str:
        """Build Authorization header value."""
        return f"{self._TOKEN_TYPE} {self._token}"

    async def change_people(self, modem: str, people: str) -> Any:
        """Change household composition setting."""
        _LOGGER.info("Changing household composition to: %s", people)
        return await self._send_command(modem, "changePeople", 0, people)

    async def change_antilegio(self, modem: str, antilegio: str) -> Any:
        """Change antilegio cycle setting."""
        _LOGGER.info("Changing antilegionella cycle to: %s", antilegio)
        return await self._send_command(modem, "antilegio", 0, antilegio)

    async def change_week_planning(
        self, modem: str, planning_str: str, mode: str = "A"
    ) -> Any:
        """Change week planning for mode A or B."""
        method = f"changePlanningMode{mode}"
        _LOGGER.info("Changing week planning (mode %s): %s", mode, planning_str)
        return await self._send_command(modem, method, 1, planning_str)

    async def set_holidays_mode(
        self, modem: str, start_date: str, end_date: str
    ) -> Any:
        """
        Set holidays mode with start and end dates.

        Args:
            modem: Device modem ID
            start_date: Start date in format yyyyMMddHHmmssZ (e.g., 20251220000000Z)
            end_date: End date in format yyyyMMddHHmmssZ (e.g., 20260105000000Z)

        Returns:
            API response

        """
        # Format: W + start_date + end_date (concatenated with W prefix)
        param = f"W{start_date}{end_date}"
        _LOGGER.info(
            "Setting holidays mode for modem %s from %s to %s",
            modem,
            start_date,
            end_date,
        )
        return await self._send_command(modem, "changeMode", 1, param)

    async def cancel_holidays_mode(self, modem: str) -> Any:
        """
        Cancel holidays mode by setting dates to 0001-01-01.

        Returns:
            API response

        """
        # Special format to cancel: W + two dates at epoch start
        param = "W00010101000000Z00010101000000Z"
        _LOGGER.info("Cancelling holidays mode for modem %s", modem)
        return await self._send_command(modem, "changeMode", 1, param)

    async def set_frost_protection_mode(self, modem: str, start_date: str) -> Any:
        """
        Set frost protection mode (hors gel) with start date and no end date.

        Args:
            modem: Device modem ID
            start_date: Start date in format yyyyMMddHHmmssZ (e.g., 20251220000000Z)

        Returns:
            API response

        """
        # Format: W + start_date + 00000000000000Z (no end date for frost protection)
        param = f"W{start_date}00000000000000Z"
        _LOGGER.info(
            "Setting frost protection mode for modem %s from %s",
            modem,
            start_date,
        )
        return await self._send_command(modem, "changeMode", 1, param)

    async def reset_filter(self, modem: str) -> Any:
        """Reset filter wear indicator."""
        _LOGGER.info("Resetting filter for modem %s", modem)
        async with await self._request_with_auth_interceptor(
            self._session.patch,
            f"{self._API_URL_PRODUCTS}/{modem}/resetFilter",
        ) as response:
            result = await response.json()
            _LOGGER.debug("Reset filter response: %s", result)
            return result

    async def _send_command(self, modem: str, method: str, uid: int, param: str) -> Any:
        """Send JSON-RPC command to device."""
        json_payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": uid,
            "params": [param],
        }
        _LOGGER.info(
            "Sending command: %s to modem %s",
            method,
            modem,
        )
        _LOGGER.debug("Command payload: %s", json_payload)
        async with await self._request_with_auth_interceptor(
            self._session.post,
            f"{self._API_URL_PRODUCTS}/{modem}/commands",
            json=json_payload,
        ) as response:
            result = await response.json()
            _LOGGER.debug("Command response: %s", result)
            return result

    async def get_statistics(
        self, modem: str, start_date: str, end_date: str, granularity: str = "month"
    ) -> dict[str, Any] | None:
        """
        Get device statistics.

        Args:
            modem: Device modem ID
            start_date: Start date in format yyyyMMddHHmmssZ (e.g., 20250101000000Z)
            end_date: End date in format yyyyMMddHHmmssZ (e.g., 20251231235959Z)
            granularity: Statistics granularity - 'day', 'week', or 'month'

        Returns:
            Statistics data or None if request fails

        """
        url = (
            f"{self._API_URL_PRODUCTS}/{modem}/statistics/"
            f"{start_date}/{end_date}/{granularity}"
        )

        try:
            async with await self._request_with_auth_interceptor(
                self._session.get,
                url,
            ) as response:
                if response.status == HTTP_OK:
                    return await response.json()
                _LOGGER.error("Failed to get statistics: %s", response.status)
                return None
        except Exception as e:
            _LOGGER.error("Error fetching statistics: %s", e)
            return None


class AuthenticationError(Exception):
    """Authentication failed exception."""
