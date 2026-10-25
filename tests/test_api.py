"""Tests for the Local API client, reproducing the quirks of the real clock."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.puri_nixie_clock.api import (
    CannotConnect,
    InvalidResponse,
    ParameterNotSupported,
    PuriClockClient,
)
from custom_components.puri_nixie_clock.const import MAX_ATTEMPTS

BASE = "http://clock.test:88/v1"
HTML_PAGE = "<!doctype html><html><title>Clock Configuration</title></html>"
NOT_FOUND = {"ok": False, "status": 404, "message": "Setting not found or returned 0"}


def _html(method: str, param: str) -> AiohttpClientMockResponse:
    return AiohttpClientMockResponse(method, URL(f"{BASE}/{param}"), text=HTML_PAGE)


def _ok(method: str, param: str, value: int) -> AiohttpClientMockResponse:
    return AiohttpClientMockResponse(
        method, URL(f"{BASE}/{param}"), json={"ok": True, "status": 200, "value": value}
    )


def _sequence(
    mocker: AiohttpClientMocker,
    method: str,
    param: str,
    responses: list[AiohttpClientMockResponse],
) -> None:
    """Serve the given responses one after the other for one URL."""
    queue = iter(responses)

    async def side_effect(method: str, url: URL, data: object) -> AiohttpClientMockResponse:
        return next(queue)

    mocker.request(method, f"{BASE}/{param}", side_effect=side_effect)


def _client(hass: HomeAssistant) -> PuriClockClient:
    return PuriClockClient(async_get_clientsession(hass), "clock.test", 88)


async def test_get_returns_value(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/brightnessday", json={"ok": True, "status": 200, "value": 201})
    assert await _client(hass).get("brightnessday") == 201


@pytest.mark.parametrize("status", [404, 405])
async def test_get_unsupported_parameter(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    aioclient_mock.get(f"{BASE}/macaddr", status=status, json={**NOT_FOUND, "status": status})
    with pytest.raises(ParameterNotSupported):
        await _client(hass).get("macaddr")


async def test_get_html_page_is_invalid(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The clock answers `format`, `firmware` and `freememory` with HTML and HTTP 200."""
    aioclient_mock.get(f"{BASE}/format", text=HTML_PAGE)
    with pytest.raises(InvalidResponse):
        await _client(hass).get("format")
    assert aioclient_mock.call_count == MAX_ATTEMPTS


async def test_get_malformed_json(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/rssi", text='{"ok": tru')
    with pytest.raises(InvalidResponse):
        await _client(hass).get("rssi")


async def test_get_ok_false(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE}/rssi", json={"ok": False, "status": 400, "message": "nope"})
    with pytest.raises(InvalidResponse):
        await _client(hass).get("rssi")


@pytest.mark.parametrize("value", ["1.40", None, True, 1.5])
async def test_get_non_integer_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, value: object
) -> None:
    aioclient_mock.get(f"{BASE}/rssi", json={"ok": True, "status": 200, "value": value})
    with pytest.raises(InvalidResponse):
        await _client(hass).get("rssi")


async def test_get_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/rssi", exc=aiohttp.ClientConnectionError)
    with pytest.raises(CannotConnect):
        await _client(hass).get("rssi")
    assert aioclient_mock.call_count == 1


async def test_get_retries_once_on_timeout(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/rssi", exc=TimeoutError)
    with pytest.raises(CannotConnect):
        await _client(hass).get("rssi")
    assert aioclient_mock.call_count == 2


async def test_get_recovers_after_one_timeout(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    responses = iter(
        [
            AiohttpClientMockResponse("GET", URL(f"{BASE}/rssi"), exc=TimeoutError),
            AiohttpClientMockResponse(
                "GET", URL(f"{BASE}/rssi"), json={"ok": True, "status": 200, "value": -69}
            ),
        ]
    )

    async def side_effect(method: str, url: URL, data: object) -> AiohttpClientMockResponse:
        return next(responses)

    aioclient_mock.get(f"{BASE}/rssi", side_effect=side_effect)

    assert await _client(hass).get("rssi") == -69
    assert aioclient_mock.call_count == 2


async def test_set_sends_json_and_returns_value_read_back(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The POST response is the register value (written minus 1), the GET is the truth."""
    aioclient_mock.post(f"{BASE}/brightnessday", json={"ok": True, "status": 200, "value": 125})
    aioclient_mock.get(f"{BASE}/brightnessday", json={"ok": True, "status": 200, "value": 126})

    assert await _client(hass).set("brightnessday", 126) == 126

    assert [call[0] for call in aioclient_mock.mock_calls] == ["POST", "GET"]
    assert aioclient_mock.mock_calls[0][2] == {"value": 126}


async def test_set_value_one_is_sent_as_json(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A plain `1` makes the clock return its HTML page; JSON works."""
    aioclient_mock.post(f"{BASE}/brightnessday", json={"ok": True, "status": 200, "value": 0})
    aioclient_mock.get(f"{BASE}/brightnessday", json={"ok": True, "status": 200, "value": 1})

    assert await _client(hass).set("brightnessday", 1) == 1
    assert aioclient_mock.mock_calls[0][2] == {"value": 1}


async def test_set_html_response_is_retried_then_invalid_without_read_back(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/brightnessday", text=HTML_PAGE)
    with pytest.raises(InvalidResponse):
        await _client(hass).set("brightnessday", 1)
    assert [call[0] for call in aioclient_mock.mock_calls] == ["POST"] * MAX_ATTEMPTS


async def test_get_recovers_after_html_answers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The clock answers about one request in five with its HTML page."""
    _sequence(
        aioclient_mock,
        "GET",
        "rssi",
        [_html("GET", "rssi")] * (MAX_ATTEMPTS - 1) + [_ok("GET", "rssi", -69)],
    )
    assert await _client(hass).get("rssi") == -69
    assert aioclient_mock.call_count == MAX_ATTEMPTS


async def test_set_recovers_after_html_answers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    _sequence(
        aioclient_mock,
        "POST",
        "brightnessday",
        [
            _html("POST", "brightnessday"),
            _html("POST", "brightnessday"),
            _ok("POST", "brightnessday", 125),
        ],
    )
    _sequence(
        aioclient_mock,
        "GET",
        "brightnessday",
        [_html("GET", "brightnessday"), _ok("GET", "brightnessday", 126)],
    )

    assert await _client(hass).set("brightnessday", 126) == 126
    assert [call[0] for call in aioclient_mock.mock_calls] == ["POST"] * 3 + ["GET"] * 2


async def test_unsupported_parameter_is_not_retried(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/macaddr", status=404, json=NOT_FOUND)
    with pytest.raises(ParameterNotSupported):
        await _client(hass).get("macaddr")
    assert aioclient_mock.call_count == 1


async def test_set_unsupported_parameter(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(f"{BASE}/rssi", status=405, json={**NOT_FOUND, "status": 405})
    with pytest.raises(ParameterNotSupported):
        await _client(hass).set("rssi", 1)
