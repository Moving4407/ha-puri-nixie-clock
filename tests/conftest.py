"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.puri_nixie_clock.const import DOMAIN

HOST = "clock.test"
PORT = 88
BASE = f"http://{HOST}:{PORT}/v1"
SERIAL = "12345"

# Values as read from the real clock (docs/clock-probe-report.md).
CLOCK_VALUES = {
    "brightnessday": 201,
    "brightnessnight": 1,
    "currentdisplayedvalue": 1125,
    "rssi": -69,
    "productid": 6,
    "serialnumber": int(SERIAL),
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the custom integration under test."""


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not wait between retries of an HTML answer."""
    monkeypatch.setattr("custom_components.puri_nixie_clock.api.RETRY_DELAY", 0)


@pytest.fixture
def expected_lingering_timers() -> bool:
    """The `sun` dependency, loaded with the integration, leaves its own timers running."""
    return True


def mock_clock(aioclient_mock: AiohttpClientMocker, **overrides: int) -> None:
    """Answer every parameter the integration reads, as the clock does."""
    for param, value in {**CLOCK_VALUES, **overrides}.items():
        aioclient_mock.get(f"{BASE}/{param}", json={"ok": True, "status": 200, "value": value})


class FakeClock:
    """A stateful clock behind the mocked HTTP session.

    Behaves like the real one where it matters: the POST response is the written value
    minus 1 and the next GET returns the written value. Only the two brightness
    parameters may be written; anything else fails the test.
    """

    WRITABLE = ("brightnessday", "brightnessnight")

    def __init__(self, mocker: AiohttpClientMocker, **values: int) -> None:
        """Register the clock on the mocked session."""
        self.values = {**CLOCK_VALUES, **values}
        self.writes: list[tuple[str, int]] = []
        self.html_on_write = False  # answer every POST with the HTML page
        self.ignore_writes = False  # accept writes but keep the old value
        for param in self.values:
            mocker.request("GET", f"{BASE}/{param}", side_effect=self._get)
            mocker.request("POST", f"{BASE}/{param}", side_effect=self._post)

    @staticmethod
    def _param(url: URL) -> str:
        return url.path.rsplit("/", 1)[-1]

    async def _get(self, method: str, url: URL, data: object) -> AiohttpClientMockResponse:
        body = {"ok": True, "status": 200, "value": self.values[self._param(url)]}
        return AiohttpClientMockResponse(method, url, json=body)

    async def _post(self, method: str, url: URL, data: dict) -> AiohttpClientMockResponse:
        param = self._param(url)
        assert param in self.WRITABLE, f"the integration must not write {param}"
        if self.html_on_write:
            return AiohttpClientMockResponse(method, url, text="<!doctype html><html></html>")
        value = data["value"]
        self.writes.append((param, value))
        if not self.ignore_writes:
            self.values[param] = value
        body = {"ok": True, "status": 200, "value": value - 1}
        return AiohttpClientMockResponse(method, url, json=body)


@pytest.fixture
def clock(aioclient_mock: AiohttpClientMocker) -> FakeClock:
    """A fake clock showing the values of the real one."""
    return FakeClock(aioclient_mock)


@pytest.fixture
def sun_elevation(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Control the solar elevation the integration sees; set `.value` to None for none."""
    holder = SimpleNamespace(value=10.0)
    monkeypatch.setattr(
        "custom_components.puri_nixie_clock.controller.get_sun_elevation", lambda hass: holder.value
    )
    return holder


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add the entry (unless a test already did) and set it up."""
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Look up an entity of the clock by platform and key."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}")
    assert found is not None, f"no {platform} entity {key}"
    return found


def service(hass: HomeAssistant) -> Callable[..., object]:
    """Return a blocking service caller."""

    async def call(domain: str, name: str, entity: str, **data: object) -> None:
        await hass.services.async_call(domain, name, {"entity_id": entity, **data}, blocking=True)

    return call


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured clock."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        data={"host": HOST, "port": PORT, "product_id": 6},
        title="Puri Nixie Clock",
    )
