"""Sample API Client."""

import asyncio
from typing import Any

import aiohttp

from custom_components.aldes.entity import DataApiEntity

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401


class AldesApi:
    """Aldes API client."""

    _API_URL_TOKEN = "https://aldesiotsuite-aldeswebapi.azurewebsites.net/oauth2/token"  # noqa: S105
    _API_URL_PRODUCTS = "https://aldesiotsuite-aldeswebapi.azurewebsites.net/aldesoc/v5/users/me/products"  # pylint: disable=line-too-long
    _AUTHORIZATION_HEADER_KEY = "Authorization"
    _TOKEN_TYPE = "Bearer"  # noqa: S105

    def __init__(
        self, username: str, password: str, session: aiohttp.ClientSession
    ) -> None:
        """Sample API Client."""
        self._username = username
        self._password = password
        self._session = session
        self._token = ""
        self.queue_target_temperature = asyncio.Queue()

        asyncio.create_task(self.worker())

    async def authenticate(self) -> None:
        """Get an access token."""
        data: dict = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
        }

        async with self._session.post(self._API_URL_TOKEN, data=data) as response:
            json = await response.json()
            if response.status == HTTP_OK:
                self._token = json["access_token"]
            else:
                raise AuthenticationExceptionError

    async def change_mode(self, modem: str, mode: str, is_for_hot_water: bool) -> Any:
        """Change mode."""
        return await self._send_command(
            modem, "changeMode", 2 if is_for_hot_water else 1, mode
        )

    async def fetch_data(self) -> Any:
        """Fetch data."""
        async with await self._request_with_auth_interceptor(
            self._session.get, self._API_URL_PRODUCTS
        ) as response:
            data = await response.json()

            if isinstance(data, list) and len(data) > 0:
                return DataApiEntity(data[0])

            return None

    async def worker(self) -> None:
        """Traite les tâches dans la file avec un délai entre chaque tâche."""
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
                await asyncio.sleep(5)
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
            return await response.json()

    async def _request_with_auth_interceptor(
        self, request: Any, url: str, **kwargs: Any
    ) -> Any:
        """Provide authentication to request."""
        initial_response = await request(
            url,
            headers={self._AUTHORIZATION_HEADER_KEY: self._build_authorization()},
            **kwargs,
        )
        if initial_response.status == HTTP_UNAUTHORIZED:
            initial_response.close()
            await self.authenticate()
            return request(
                url,
                headers={self._AUTHORIZATION_HEADER_KEY: self._build_authorization()},
                **kwargs,
            )
        return initial_response

    def _build_authorization(self) -> str:
        """Build authorization."""
        return f"{self._TOKEN_TYPE} {self._token}"

    async def process_queue(self) -> None:
        """Process requests in the queue with a delay."""
        while True:
            (
                func,
                args,
                kwargs,
            ) = await self.queue_target_temperature.get()
            await func(*args, **kwargs)
            await asyncio.sleep(5)
            self.queue_target_temperature.task_done()

    async def change_people(self, modem: str, people: str) -> Any:
        """Change people."""
        return await self._send_command(modem, "changePeople", 0, people)

    async def change_antilegio(self, modem: str, antilegio: str) -> Any:
        """Change antilegio."""
        return await self._send_command(modem, "antilegio", 0, antilegio)

    async def _send_command(self, modem: str, method: str, uid: int, param: str) -> Any:
        """Send command."""
        async with await self._request_with_auth_interceptor(
            self._session.post,
            f"{self._API_URL_PRODUCTS}/{modem}/commands",
            json={
                "jsonrpc": "2.0",
                "method": method,
                "id": uid,
                "params": [param],
            },
        ) as response:
            return await response.json()


class AuthenticationExceptionError(Exception):
    """Exception."""
