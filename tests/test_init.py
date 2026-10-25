"""Tests for setup, the coordinator and the sensors."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.puri_nixie_clock.const import DOMAIN

from .conftest import BASE, SERIAL, mock_clock


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _sensor_id(hass: HomeAssistant, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_{key}")
    assert entity_id is not None
    return entity_id


async def _poll(hass: HomeAssistant, seconds: int = 31) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_setup_creates_device_and_sensors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_clock(aioclient_mock)
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(_sensor_id(hass, "displayed_value")).state == "1125"
    wifi = hass.states.get(_sensor_id(hass, "wifi_signal"))
    assert wifi.state == "-69"
    assert wifi.attributes["unit_of_measurement"] == "dBm"
    assert wifi.attributes["device_class"] == "signal_strength"

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SERIAL), config_entry.entry_id
    )
    assert device.manufacturer == "Dalibor Farny"
    assert device.model == "Puri Nixie Clock (4-tube)"
    assert not device.connections

    entry = er.async_get(hass).async_get(_sensor_id(hass, "wifi_signal"))
    assert entry.entity_category == "diagnostic"
    assert entry.disabled_by is None


async def test_setup_only_reads(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_clock(aioclient_mock)
    await _setup(hass, config_entry)

    assert {call[0] for call in aioclient_mock.mock_calls} == {"GET"}


async def test_setup_not_ready_when_clock_unreachable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    aioclient_mock.get(f"{BASE}/brightnessday", exc=aiohttp.ClientConnectionError)
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_clock(aioclient_mock)
    await _setup(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_unavailable_and_recovery_log_once_per_outage(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    caplog,
) -> None:
    mock_clock(aioclient_mock)
    await _setup(hass, config_entry)
    entity_id = _sensor_id(hass, "displayed_value")
    caplog.set_level(logging.INFO)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/brightnessday", exc=aiohttp.ClientConnectionError)
    for _ in range(3):
        await _poll(hass)
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    assert sum("Error fetching" in r.message for r in caplog.records) == 1

    aioclient_mock.clear_requests()
    mock_clock(aioclient_mock, currentdisplayedvalue=1200)
    await _poll(hass)
    assert hass.states.get(entity_id).state == "1200"
    assert sum("recovered" in r.message for r in caplog.records) == 1


async def test_html_answer_makes_entities_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    mock_clock(aioclient_mock)
    await _setup(hass, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/brightnessday", text="<!doctype html><html></html>")
    await _poll(hass)

    assert hass.states.get(_sensor_id(hass, "wifi_signal")).state == STATE_UNAVAILABLE
