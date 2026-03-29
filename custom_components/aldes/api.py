"""Aldes API client."""

import asyncio
import base64
import contextlib
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any, NoReturn

import aiohttp
import backoff
from aiohttp import ClientError, ClientResponseError, ClientTimeout

from custom_components.aldes.models import ApiHealthState, CommandUid, DataApiEntity

_LOGGER = logging.getLogger(__name__)

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401


def _raise_client_error(message: str) -> NoReturn:
    """Raise a client error with a message."""
    raise ClientError(message)


REQUEST_DELAY = 5  # Delay between queued requests in seconds
CACHE_TTL = 300  # Cache TTL in seconds (5 minutes)
TEMPERATURE_CHANGE_MAX_RETRIES = 3  # Max retries for temperature changes in worker
STATE_CHANGE_BACKOFF_MAX_TRIES = (
    4  # Max tries with exponential backoff for state changes
)


def _backoff_handler(details: dict[str, Any]) -> None:
    """Log backoff attempts and update health state."""
    target_self = details["args"][0]
    if isinstance(target_self, AldesApi):
        target_self.health_state = ApiHealthState.RETRYING
    _LOGGER.warning(
        "Backing off %s(...) for %.1fs (%s)",
        details["target"].__name__,
        details["wait"],
        details["exception"],
    )


def _is_reauth_error(e: BaseException) -> bool:
    """Return True if this is an error that should trigger re-authentication."""
    return isinstance(e, ClientResponseError) and e.status == HTTP_UNAUTHORIZED


class AldesApi:
    """Aldes API client."""

    _API_URL_BASE = "https://aldesiotsuite-aldeswebapi.azurewebsites.net"
    _API_URL_TOKEN = f"{_API_URL_BASE}/oauth2/token"
    _API_URL_PRODUCTS = f"{_API_URL_BASE}/aldesoc/v5/users/me/products"  # pylint: disable=line-too-long

    _AUTHORIZATION_HEADER_KEY = "Authorization"
    _TOKEN_TYPE = "Bearer"

    # Constants from official app analysis
    _API_KEY = "XQibgk1ozo1wjVQcvcoFQqMl3pjEwcRv"
    _USER_AGENT = "AldesConnect/4.21"
    _SDK_VERSION = "a:17.0.0"

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        token: str = "",
    ) -> None:
        """Initialize Aldes API client."""
        self._username = username
        self._password = password
        self._session = session
        self._token = token
        self._timeout = ClientTimeout(total=30)
        self._cache: dict[str, Any] = {}
        self._cache_timestamp: dict[str, datetime] = {}
        self.health_state: ApiHealthState = ApiHealthState.ONLINE
        self.queue_target_temperature: (
            asyncio.Queue[tuple[str, int, str, Any]] | None
        ) = None
        self._temperature_task: asyncio.Task[None] | None = None
        # Track pending command verifications for retry if not applied
        self._pending_verifications: dict[str, Any] = {}

    async def _ensure_temperature_worker_started(self) -> None:
        """Ensure the temperature worker task is started."""
        if self._temperature_task is None or self._temperature_task.done():
            _LOGGER.debug("Starting temperature worker task")
            if self.queue_target_temperature is None:
                self.queue_target_temperature = asyncio.Queue()
            self._temperature_task = asyncio.create_task(self._temperature_worker())
        else:
            _LOGGER.debug("Temperature worker task already running")

    async def stop_temperature_worker(self) -> None:
        """Stop the temperature worker and wait for queue to empty."""
        if self._temperature_task and not self._temperature_task.done():
            # Wait for queue to be processed
            if self.queue_target_temperature:
                try:
                    await asyncio.wait_for(
                        self.queue_target_temperature.join(), timeout=10
                    )
                except asyncio.TimeoutError:
                    _LOGGER.warning("Temperature queue did not empty in time")

            # Cancel the worker task
            self._temperature_task.cancel()
            try:
                await self._temperature_task
            except asyncio.CancelledError:
                pass

    def register_pending_verification(
        self, verification_id: str, metadata: dict[str, Any]
    ) -> None:
        """
        Register a pending command verification to check later if applied.

        Args:
            verification_id: Unique ID for this verification (e.g., "modem_temp_123")
            metadata: Dict with verification details (command, modem, retry_fn, etc)

        """
        self._pending_verifications[verification_id] = {
            "metadata": metadata,
            "registered_at": datetime.now(UTC),
        }
        _LOGGER.debug(
            "Registered pending verification %s",
            verification_id,
        )
        self._temperature_task: asyncio.Task[Any] | None = None
        # Track pending command verifications for retry if not applied
        self._pending_verifications: dict[str, Any] = {}

    def unregister_pending_verification(self, verification_id: str) -> None:
        """Mark a verification as complete (command was applied correctly)."""
        if verification_id in self._pending_verifications:
            del self._pending_verifications[verification_id]
            _LOGGER.debug(
                "Cleared pending verification %s",
                verification_id,
            )

    def get_pending_verifications(
        self, timeout_seconds: int = 60
    ) -> dict[str, dict[str, Any]]:
        """
        Get all pending verifications that should be checked now.

        Returns verifications that have been pending for at least timeout_seconds.
        This is used by the coordinator to periodically check if commands were
        actually applied, and retry if not.

        Args:
            timeout_seconds: Only return verifications older than this

        Returns:
            Dict of {verification_id: metadata} for verifications to check

        """
        now = datetime.now(UTC)
        pending = {}
        for vid, data in list(self._pending_verifications.items()):
            age = (now - data["registered_at"]).total_seconds()
            if age >= timeout_seconds:
                pending[vid] = data["metadata"]
        return pending

    def _log_request_details(
        self, method: str, url: str, headers: dict, data: Any = None
    ) -> None:
        """Log request details for debugging with sensitive data masking."""
        _LOGGER.debug("=== Request Details ===")
        _LOGGER.debug("Method: %s", method)
        _LOGGER.debug("URL: %s", url)
        # Log headers excluding sensitive auth info if needed
        safe_headers = {
            k: v for k, v in headers.items() if k.lower() != "authorization"
        }
        _LOGGER.debug("Headers: %s", safe_headers)

        if data:
            safe_data = data
            if isinstance(data, dict) and "password" in data:
                safe_data = data.copy()
                safe_data["password"] = "***"
            _LOGGER.debug("Data: %s", safe_data)

    def _log_api_performance(
        self, url: str, method: str, status: int, duration_ms: float
    ) -> None:
        """Log API performance metrics for diagnostics."""
        _LOGGER.debug(
            "API %s %s completed with status %d in %.2f ms",
            method.upper(),
            url.split("/")[-1],
            status,
            duration_ms,
        )

    @backoff.on_exception(
        backoff.expo,
        (ClientError, TimeoutError),
        max_tries=3,
        max_time=60,
        on_backoff=_backoff_handler,
    )
    async def authenticate(self) -> None:
        """Authenticate and retrieve access token from Aldes API."""
        _LOGGER.info("Authenticating with Aldes API...")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": self._USER_AGENT,
            "apikey": self._API_KEY,
            "sdkVersion": self._SDK_VERSION,
        }

        data: dict[str, str] = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "scope": "openid profile email offline_access",
        }

        self._log_request_details("POST", self._API_URL_TOKEN, headers, data)

        try:
            async with self._session.post(
                self._API_URL_TOKEN, data=data, headers=headers, timeout=self._timeout
            ) as response:
                response.raise_for_status()
                json_resp = await response.json()
                self._token = json_resp["access_token"]
                self.health_state = ApiHealthState.ONLINE
                _LOGGER.info("Successfully authenticated with Aldes API")
        except (ClientError, TimeoutError) as err:
            self.health_state = ApiHealthState.OFFLINE
            error_msg = f"Authentication request failed: {err}"
            _LOGGER.exception(error_msg)
            raise AuthenticationError(error_msg) from err

    async def async_close(self) -> None:
        """Cleanup background tasks."""
        if self._temperature_task and not self._temperature_task.done():
            self._temperature_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._temperature_task

    def register_pending_verification(
        self, verification_id: str, metadata: dict[str, Any]
    ) -> None:
        """
        Register a pending command verification to check later if applied.

        Args:
            verification_id: Unique ID for this verification (e.g., "modem_temp_123")
            metadata: Dict with verification details (command, modem, retry_fn, etc)

        """
        self._pending_verifications[verification_id] = {
            "metadata": metadata,
            "registered_at": datetime.now(UTC),
        }
        _LOGGER.debug(
            "Registered pending verification %s",
            verification_id,
        )

    def unregister_pending_verification(self, verification_id: str) -> None:
        """Mark a verification as complete (command was applied correctly)."""
        if verification_id in self._pending_verifications:
            del self._pending_verifications[verification_id]
            _LOGGER.debug(
                "Cleared pending verification %s",
                verification_id,
            )

    def get_pending_verifications(
        self, timeout_seconds: int = 60
    ) -> dict[str, dict[str, Any]]:
        """
        Get all pending verifications that should be checked now.

        Returns verifications that have been pending for at least timeout_seconds.
        This is used by the coordinator to periodically check if commands were
        actually applied, and retry if not.

        Args:
            timeout_seconds: Only return verifications older than this

        Returns:
            Dict of {verification_id: metadata} for verifications to check

        """
        now = datetime.now(UTC)
        pending = {}
        for vid, data in list(self._pending_verifications.items()):
            age = (now - data["registered_at"]).total_seconds()
            if age >= timeout_seconds:
                pending[vid] = data["metadata"]
        return pending

    @backoff.on_exception(
        backoff.expo,
        (ClientError, TimeoutError, ClientResponseError),
        max_tries=5,
        max_time=300,
        on_backoff=_backoff_handler,
        giveup=lambda e: isinstance(e, ClientResponseError) and 400 <= e.status < 500,
    )
    async def _api_request(
        self, method: str, url: str, **kwargs: Any
    ) -> list[Any] | dict[str, Any]:
        """Execute API request with retry, timeout and error handling."""
        cache_key = f"{method}:{url}"
        start_time = datetime.now(UTC)

        try:
            if "timeout" not in kwargs:
                kwargs["timeout"] = self._timeout

            request_func = getattr(self._session, method.lower())

            async with await self._request_with_auth_interceptor(
                request_func, url, **kwargs
            ) as response:
                if response.status == HTTP_OK:
                    dduration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
                    response.raise_for_status()
                    data = await response.json()
                    self._cache[cache_key] = data
                    self._cache_timestamp[cache_key] = datetime.now(UTC)
                    self.health_state = ApiHealthState.ONLINE
                    self._log_api_performance(url, method, response.status, duration_ms)
                    _LOGGER.debug("Stored data in emergency cache for %s", cache_key)
                    return data
                msg = f"API request failed with status {response.status}"
                _LOGGER.error(msg)
                _raise_client_error(msg)
        except Exception as err:
            if isinstance(err, ClientError | TimeoutError):
                _LOGGER.exception("API request error")
            elif isinstance(err, KeyError | ValueError):
                _LOGGER.exception("Error parsing API response")
            else:
                _LOGGER.exception("Unexpected error during API request")

            if cache_key in self._cache:
                cache_age = datetime.now(UTC) - self._cache_timestamp.get(
                    cache_key, datetime.min.replace(tzinfo=UTC)
                )
                self.health_state = ApiHealthState.DEGRADED
                _LOGGER.warning(
                    "Using cached data as fallback due to error: %s (age: %s)",
                    type(err).__name__,
                    cache_age,
                )
                return self._cache[cache_key]

            self.health_state = ApiHealthState.OFFLINE
            if isinstance(err, KeyError | ValueError):
                msg = f"Invalid API response: {err}"
                raise ClientError(msg) from err
            raise

    @backoff.on_exception(
        backoff.expo,
        (ClientError, TimeoutError),
        max_tries=STATE_CHANGE_BACKOFF_MAX_TRIES,
        max_time=30,
        logger=None,  # Disable backoff logger to avoid duplicate logs
    )
    async def change_mode(self, modem: str, mode: str, uid: CommandUid) -> Any:
        """Change mode (air or hot water) with automatic retry on failure."""
        mode_type = "air" if uid == CommandUid.AIR_MODE else "hot water"
        _LOGGER.info("Changing %s mode to: %s", mode_type, mode)
        return await self._send_command(modem, "changeMode", uid, mode)

    async def fetch_data(self) -> dict[str, DataApiEntity]:
        """Fetch data."""
        _LOGGER.debug("Fetching data from Aldes API...")
        try:
            data = await self._api_request("get", self._API_URL_PRODUCTS)
        except (ClientError, TimeoutError):
            _LOGGER.exception("Failed to fetch data")
            return {}
        else:
            _LOGGER.debug("Fetched data: %s", data)

            if isinstance(data, list) and len(data) > 0:
                devices: dict[str, DataApiEntity] = {}
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    modem = item.get("modem")
                    if not modem:
                        continue
                    devices[modem] = DataApiEntity(item)
                if devices:
                    _LOGGER.debug(
                        "Successfully retrieved Aldes device data: %d devices",
                        len(devices),
                    )
                    return devices

            _LOGGER.warning("No data received from Aldes API")
            return {}

    async def _temperature_worker(self) -> None:
        """Process temperature change requests from queue with delay between each."""
        _LOGGER.info("Temperature worker started")
        while True:
            try:
                if self.queue_target_temperature is None:
                    _LOGGER.debug("Queue is None, waiting...")
                    await asyncio.sleep(1)
                    continue

                _LOGGER.debug("Worker waiting for next item in queue...")
                (
                    modem,
                    thermostat_id,
                    thermostat_name,
                    temperature,
                ) = await self.queue_target_temperature.get()

                _LOGGER.debug(
                    "Worker processing item: %s, %s, %s, %s",
                    modem,
                    thermostat_id,
                    thermostat_name,
                    temperature,
                )

                if modem and thermostat_id and thermostat_name and temperature:
                    try:
                        await self.change_temperature(
                            modem, thermostat_id, thermostat_name, temperature
                        )
                    except Exception:
                        _LOGGER.exception(
                            "Error changing temperature for %s. Worker continuing.",
                            thermostat_name,
                        )

                    _LOGGER.debug("Worker sleeping for %s seconds", REQUEST_DELAY)
                    await asyncio.sleep(REQUEST_DELAY)
                
                # Mark task as done immediately after processing
                self.queue_target_temperature.task_done()
                
            except asyncio.CancelledError:
                _LOGGER.info("Temperature worker cancelled")
                break
            except Exception:
                _LOGGER.exception("Unexpected error in temperature worker")
                # In case of error, we still need to mark task as done if we got an item
                if self.queue_target_temperature is not None:
                    with contextlib.suppress(ValueError):
                        self.queue_target_temperature.task_done()
                await asyncio.sleep(REQUEST_DELAY)

    async def set_target_temperature(
        self,
        modem: str,
        thermostat_id: int,
        thermostat_name: str,
        target_temperature: Any,
    ) -> None:
        """Set target temperature."""
        await self._ensure_temperature_worker_started()
        if self.queue_target_temperature:
            _LOGGER.debug(
                "Queueing temperature change for %s: %s",
                thermostat_name,
                target_temperature,
            )
            await self.queue_target_temperature.put(
                (modem, thermostat_id, thermostat_name, target_temperature)
            )
        else:
            _LOGGER.error("Failed to queue temperature change: Queue is None")

    @backoff.on_exception(
        backoff.expo,
        (ClientError, TimeoutError),
        max_tries=STATE_CHANGE_BACKOFF_MAX_TRIES,
        max_time=30,
        logger=None,  # Disable backoff logger to avoid duplicate logs
    )
    async def change_temperature(
        self,
        modem: str,
        thermostat_id: int,
        thermostat_name: str,
        target_temperature: Any,
    ) -> Any:
        """Change temperature of thermostat with automatic retry on failure."""
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

    @backoff.on_exception(
        backoff.expo,
        ClientResponseError,
        max_tries=2,
        giveup=lambda e: not _is_reauth_error(e),
        on_backoff=_backoff_handler,
    )
    async def _request_with_auth_interceptor(
        self, request: Any, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Execute request with automatic re-authentication if needed."""
        headers = kwargs.get("headers", {})
        headers[self._AUTHORIZATION_HEADER_KEY] = self._build_authorization()
        headers["apikey"] = self._API_KEY
        headers["User-Agent"] = self._USER_AGENT
        headers["sdkVersion"] = self._SDK_VERSION
        kwargs["headers"] = headers

        self._log_request_details("REQ", url, headers, kwargs.get("json"))

        response = await request(url, **kwargs)

        if response.status == HTTP_UNAUTHORIZED:
            _LOGGER.info("Token expired (401), re-authenticating...")
            response.close()  # Close the initial response
            await self.authenticate()

            # Update token in headers for the retry
            kwargs["headers"][
                self._AUTHORIZATION_HEADER_KEY
            ] = self._build_authorization()
            # This will be the last attempt, so we return the response directly
            return await request(url, **kwargs)

        return response

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
        """
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
        """
        param = "W00010101000000Z00010101000000Z"
        _LOGGER.info("Cancelling holidays mode for modem %s", modem)
        return await self._send_command(modem, "changeMode", 1, param)

    async def set_kwh_prices(
        self, modem: str, kwh_pleine: float, kwh_creuse: float
    ) -> Any:
        """
        Set electricity prices for peak and off-peak hours.
        """
        pleine_milliemes = int(kwh_pleine * 1000)
        creuse_milliemes = int(kwh_creuse * 1000)
        param = f"P{pleine_milliemes}C{creuse_milliemes}"
        _LOGGER.info(
            "Setting kWh prices for modem %s: pleine=%.3f EUR/kWh, creuse=%.3f EUR/kWh",
            modem,
            kwh_pleine,
            kwh_creuse,
        )
        return await self._send_command(modem, "prixkwh", 1, param)

    async def set_frost_protection_mode(self, modem: str, start_date: str) -> Any:
        """
        Set frost protection mode (hors gel) with start date and no end date.
        """
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

    @backoff.on_exception(
        backoff.expo,
        (ClientError, TimeoutError),
        max_tries=STATE_CHANGE_BACKOFF_MAX_TRIES,
        max_time=30,
        logger=None,  # Disable backoff logger to avoid duplicate logs
    )
    async def _send_command(self, modem: str, method: str, uid: int, param: str) -> Any:
        """Send JSON-RPC command to device with automatic retry on failure."""
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

    async def check_token_validity(self) -> bool:
        """Check if the current token is still valid."""
        if not self._token:
            return False
        try:
            payload = self._token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.b64decode(payload).decode("utf-8"))
            exp = decoded.get("exp", 0)
            if exp and datetime.now(UTC).timestamp() > exp:
                _LOGGER.info("Token expired according to 'exp' field")
                return False
            await self.fetch_data()
            return True
        except Exception:
            _LOGGER.exception("Error while checking token validity")
            return False
        else:
            return True

    def get_diagnostic_info(self) -> dict[str, Any]:
        """Get diagnostic information about API client state."""
        cache_info = {
            "cached_endpoints": len(self._cache),
            "cache_details": [
                {
                    "key": key,
                    "age_seconds": (datetime.now(UTC) - timestamp).total_seconds(),
                }
                for key, timestamp in self._cache_timestamp.items()
            ],
        }

        token_info = {
            "token_present": bool(self._token),
            "token_length": len(self._token) if self._token else 0,
        }

        if self._token:
            try:
                payload = self._token.split(".")[1]
                payload += "=" * (-len(payload) % 4)
                decoded = json.loads(base64.b64decode(payload).decode("utf-8"))
                token_info["token_expires"] = datetime.fromtimestamp(
                    decoded.get("exp", 0), tz=UTC
                ).isoformat()
                token_info["token_issued_at"] = datetime.fromtimestamp(
                    decoded.get("iat", 0), tz=UTC
                ).isoformat()
            except Exception as e:
                token_info["token_decode_error"] = str(e)

        return {
            "api_url_base": self._API_URL_BASE,
            "cache": cache_info,
            "token": token_info,
            "health_state": self.health_state.value,
            "queue_active": (
                self._temperature_task is not None and not self._temperature_task.done()
            ),
        }

    @property
    def token(self) -> str:
        """Return the current access token."""
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        """Set the current access token."""
        self._token = value


class AuthenticationError(Exception):
    """Authentication failed exception."""