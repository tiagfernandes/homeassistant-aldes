"""Aldes API client."""

import asyncio
import logging
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

import aiohttp
import backoff
from aiohttp import ClientError, ClientTimeout

from custom_components.aldes.entity import DataApiEntity

_LOGGER = logging.getLogger(__name__)

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
REQUEST_DELAY = 5  # Delay between queued requests in seconds
CACHE_TTL = 300  # Cache TTL in seconds (5 minutes)


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
        self._timeout = ClientTimeout(total=30)
        self._cache: dict[str, Any] = {}
        self._cache_timestamp: dict[str, datetime] = {}
        self.queue_target_temperature: asyncio.Queue[tuple[str, int, str, Any]] = (
            asyncio.Queue()
        )
        self._temperature_task = asyncio.create_task(self._temperature_worker())

    async def authenticate(self) -> None:
        """Authenticate and retrieve access token from Aldes API."""
        _LOGGER.info("Authenticating with Aldes API...")
        data: dict[str, str] = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
        }

        try:
            async with self._session.post(
                self._API_URL_TOKEN, data=data, timeout=self._timeout
            ) as response:
                json = await response.json()
                if response.status == HTTP_OK:
                    self._token = json["access_token"]
                    _LOGGER.info("Successfully authenticated with Aldes API")
                else:
                    error_msg = f"Authentication failed with status {response.status}"
                    _LOGGER.error(error_msg)
                    raise AuthenticationError(error_msg)
        except (ClientError, TimeoutError) as err:
            error_msg = f"Authentication request failed: {err}"
            _LOGGER.exception(error_msg)
            raise AuthenticationError(error_msg) from err

    @backoff.on_exception(
        backoff.expo,
        (ClientError, TimeoutError),
        max_tries=3,
        max_time=60,
    )
    async def _api_request(
        self, method: str, url: str, **kwargs: Any
    ) -> list[Any] | dict[str, Any]:
        """Execute API request with retry, timeout and error handling."""
        # Generate cache key from method and url
        cache_key = f"{method}:{url}"

        try:
            # Add timeout to kwargs if not already present
            if "timeout" not in kwargs:
                kwargs["timeout"] = self._timeout

            request_func = getattr(self._session, method.lower())
            async with await self._request_with_auth_interceptor(
                request_func, url, **kwargs
            ) as response:
                if response.status == HTTP_OK:
                    data = await response.json()
                    # Store in cache for emergency fallback
                    self._cache[cache_key] = data
                    self._cache_timestamp[cache_key] = datetime.now(UTC)
                    _LOGGER.debug("Stored data in emergency cache for %s", cache_key)
                    return data
                msg = f"API request failed with status {response.status}"
                _LOGGER.error(msg)
                raise ClientError(msg)
        except Exception as err:
            # Log specific error type
            if isinstance(err, ClientError | TimeoutError):
                _LOGGER.exception("API request error")
            elif isinstance(err, KeyError | ValueError):
                _LOGGER.exception("Error parsing API response")
            else:
                _LOGGER.exception("Unexpected error during API request")

            # Use cached data as fallback for ANY error (regardless of age)
            if cache_key in self._cache:
                cache_age = datetime.now(UTC) - self._cache_timestamp.get(
                    cache_key, datetime.min.replace(tzinfo=UTC)
                )
                _LOGGER.warning(
                    "Using cached data as fallback due to error: %s (age: %s)",
                    type(err).__name__,
                    cache_age,
                )
                return self._cache[cache_key]

            # No cache available, propagate the error
            if isinstance(err, KeyError | ValueError):
                msg = f"Invalid API response: {err}"
                raise ClientError(msg) from err
            raise

    async def change_mode(self, modem: str, mode: str, uid: CommandUid) -> Any:
        """Change mode (air or hot water)."""
        mode_type = "air" if uid == CommandUid.AIR_MODE else "hot water"
        _LOGGER.info("Changing %s mode to: %s", mode_type, mode)
        return await self._send_command(modem, "changeMode", uid, mode)

    async def fetch_data(self) -> Any:
        """Fetch data."""
        _LOGGER.debug("Fetching data from Aldes API...")
        try:
            data = await self._api_request("get", self._API_URL_PRODUCTS)
        except (ClientError, TimeoutError):
            _LOGGER.exception("Failed to fetch data")
            return None
        else:
            _LOGGER.debug("Fetched data: %s", data)

            if isinstance(data, list) and len(data) > 0:
                # Type narrowing: data is list[Any], so data[0] is Any
                # We check if it's a dict before passing to DataApiEntity
                first_item: Any = data[0]
                if isinstance(first_item, dict):
                    _LOGGER.debug("Successfully retrieved Aldes device data")
                    return DataApiEntity(first_item)

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
        try:
            result = await self._api_request(
                "patch",
                f"{self._API_URL_PRODUCTS}/{modem}/updateThermostats",
                json=[
                    {
                        "ThermostatId": thermostat_id,
                        "Name": thermostat_name,
                        "TemperatureSet": int(target_temperature),
                    }
                ],
            )
        except (ClientError, TimeoutError):
            _LOGGER.exception("Failed to change temperature")
            raise
        else:
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

    async def set_kwh_prices(
        self, modem: str, kwh_pleine: float, kwh_creuse: float
    ) -> Any:
        """
        Set electricity prices for peak and off-peak hours.

        Args:
            modem: Device modem ID
            kwh_pleine: Peak hour price in EUR/kWh
            kwh_creuse: Off-peak hour price in EUR/kWh

        Returns:
            API response

        """
        # Convert to millièmes d'euros (multiply by 1000)
        pleine_milliemes = int(kwh_pleine * 1000)
        creuse_milliemes = int(kwh_creuse * 1000)

        # Format: P{prixPlein}C{prixCreux}
        param = f"P{pleine_milliemes}C{creuse_milliemes}"

        _LOGGER.info(
            "Setting kWh prices for modem %s: pleine=%.3f EUR/kWh (%d), "
            "creuse=%.3f EUR/kWh (%d)",
            modem,
            kwh_pleine,
            pleine_milliemes,
            kwh_creuse,
            creuse_milliemes,
        )
        return await self._send_command(modem, "prixkwh", 1, param)

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
        try:
            result = await self._api_request(
                "patch",
                f"{self._API_URL_PRODUCTS}/{modem}/resetFilter",
            )
        except (ClientError, TimeoutError):
            _LOGGER.exception("Failed to reset filter")
            raise
        else:
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
        try:
            result = await self._api_request(
                "post",
                f"{self._API_URL_PRODUCTS}/{modem}/commands",
                json=json_payload,
            )
        except (ClientError, TimeoutError):
            _LOGGER.exception("Failed to send command %s", method)
            raise
        else:
            _LOGGER.debug("Command response: %s", result)
            return result

    async def get_statistics(
        self, modem: str, start_date: str, end_date: str, granularity: str = "month"
    ) -> list[Any] | dict[str, Any] | None:
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
            return await self._api_request("get", url)
        except (ClientError, TimeoutError):
            _LOGGER.exception("Failed to get statistics")
            return None


class AuthenticationError(Exception):
    """Authentication failed exception."""
