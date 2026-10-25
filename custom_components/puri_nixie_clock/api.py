"""Async client for the Puri Nixie Clock Local API."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import MAX_ATTEMPTS, REQUEST_TIMEOUT, RETRY_DELAY


class PuriClockError(Exception):
    """Base class for client errors."""


class CannotConnect(PuriClockError):
    """The clock could not be reached (network error or timeout)."""


class InvalidResponse(PuriClockError):
    """The clock answered with something that is not a successful JSON reply."""


class NotJson(InvalidResponse):
    """The clock answered with something that is not JSON, usually its HTML page."""


class ParameterNotSupported(PuriClockError):
    """The clock does not know the parameter, or not with this method (404 or 405)."""


class PuriClockClient:
    """Talk to one clock, one request at a time.

    Quirks of the real clock (docs/clock-probe-report.md):
    - about one request in five is answered with the HTML configuration page instead
      of JSON, for any parameter; such a request was not handled, so it is retried;
    - writes are sent as JSON (a plain `1` once got the HTML page; unproven whether
      that was the glitch above);
    - the POST response holds the register value (written value minus 1), so `set`
      reads the parameter back and returns that.
    """

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = f"http://{host}:{port}/v1"
        self._lock = asyncio.Lock()

    async def get(self, param: str) -> int:
        """Read an integer parameter."""
        async with self._lock:
            return await self._get(param)

    async def set(self, param: str, value: int) -> int:
        """Write an integer parameter and return the value read back."""
        async with self._lock:
            await self._request_with_retries("POST", param, {"value": value})
            return await self._get(param)

    async def _get(self, param: str) -> int:
        """Read a parameter, retrying once on a timeout. The lock must be held."""
        try:
            data = await self._request_with_retries("GET", param)
        except CannotConnect as err:
            if not isinstance(err.__cause__, TimeoutError):
                raise
            data = await self._request_with_retries("GET", param)
        value = data.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidResponse(f"Parameter {param} returned a non-integer value: {value!r}")
        return value

    async def _request_with_retries(
        self, method: str, param: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Like `_request`, but try again when the clock answers with HTML."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._request(method, param, payload)
            except NotJson:
                if attempt == MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(RETRY_DELAY)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _request(
        self, method: str, param: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send one request and return the decoded JSON body of a successful reply."""
        url = f"{self._base_url}/{param}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(method, url, json=payload) as response:
                    status = response.status
                    text = await response.text()
        except TimeoutError as err:
            raise CannotConnect(f"Timeout talking to the clock ({method} {param})") from err
        except aiohttp.ClientError as err:
            raise CannotConnect(f"Error talking to the clock ({method} {param}): {err}") from err

        if status in (404, 405):
            raise ParameterNotSupported(f"{method} {param} is not supported (HTTP {status})")
        try:
            data = json.loads(text)
        except ValueError as err:
            raise NotJson(f"{method} {param} did not return JSON") from err
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise InvalidResponse(f"{method} {param} was not successful: {data!r}")
        return data
