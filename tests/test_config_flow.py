"""Tests for the config flow."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.puri_nixie_clock.const import DOMAIN

from .conftest import BASE, HOST, PORT, SERIAL, mock_clock

NEW_HOST = "new-clock.test"
NEW_BASE = f"http://{NEW_HOST}:{PORT}/v1"


async def _start_user_flow(hass: HomeAssistant, host: str = HOST) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": host, "port": PORT}
    )


async def test_user_flow_success(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_clock(aioclient_mock)
    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Puri Nixie Clock"
    assert result["data"] == {"host": HOST, "port": PORT, "product_id": 6}
    assert result["result"].unique_id == SERIAL


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/productid", exc=aiohttp.ClientConnectionError)
    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_response_html(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/productid", text="<!doctype html><html></html>")
    result = await _start_user_flow(hass)

    assert result["errors"] == {"base": "invalid_response"}


async def test_user_flow_serial_not_found(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A serial number of 0 is answered with a 404 by the clock."""
    mock_clock(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/productid", json={"ok": True, "status": 200, "value": 6})
    aioclient_mock.get(
        f"{BASE}/serialnumber",
        status=404,
        json={"ok": False, "status": 404, "message": "Setting not found or returned 0"},
    )
    result = await _start_user_flow(hass)

    assert result["errors"] == {"base": "invalid_response"}


async def test_user_flow_unsupported_model(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_clock(aioclient_mock, productid=99)
    result = await _start_user_flow(hass)

    assert result["errors"] == {"base": "unsupported_model"}


async def test_user_flow_six_tube_is_supported(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_clock(aioclient_mock, productid=15)
    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["product_id"] == 15


async def test_user_flow_duplicate_serial(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_clock(aioclient_mock)
    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_recovers_after_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE}/productid", exc=aiohttp.ClientConnectionError)
    result = await _start_user_flow(hass)
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_clock(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": HOST, "port": PORT}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_same_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_clock(aioclient_mock)
    for param, value in (
        ("productid", 6),
        ("serialnumber", int(SERIAL)),
        ("brightnessday", 201),
        ("brightnessnight", 1),
        ("currentdisplayedvalue", 1125),
        ("rssi", -69),
    ):
        aioclient_mock.get(f"{NEW_BASE}/{param}", json={"ok": True, "status": 200, "value": value})

    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": NEW_HOST, "port": PORT}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data["host"] == NEW_HOST


async def test_reconfigure_different_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{NEW_BASE}/productid", json={"ok": True, "status": 200, "value": 6})
    aioclient_mock.get(f"{NEW_BASE}/serialnumber", json={"ok": True, "status": 200, "value": 999})

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": NEW_HOST, "port": PORT}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert config_entry.data["host"] == HOST


async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(f"{NEW_BASE}/productid", exc=aiohttp.ClientConnectionError)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": NEW_HOST, "port": PORT}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


FULL_OPTIONS = {
    "scan_interval": 60,
    "display_on_day": "high",
    "display_on_night": "low",
    "min_value": "low",
    "max_value": "high",
    "min_elevation": -2.0,
    "max_elevation": 12.5,
}


async def _open_options(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> dict:
    config_entry.add_to_hass(hass)
    mock_clock(aioclient_mock)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    return result


async def test_options_flow_saves_all_options(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    result = await _open_options(hass, aioclient_mock, config_entry)
    result = await hass.config_entries.options.async_configure(result["flow_id"], FULL_OPTIONS)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == FULL_OPTIONS
    assert config_entry.runtime_data.coordinator.update_interval.total_seconds() == 60


async def test_options_flow_defaults(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The proposed defaults of SPEC.md section 4.4: floor 6, -6 to 10 degrees."""
    result = await _open_options(hass, aioclient_mock, config_entry)
    defaults = {str(key): key.default() for key in result["data_schema"].schema}

    assert defaults == {
        "scan_interval": 30,
        "display_on_day": "full",
        "display_on_night": "medium",
        "min_value": "very_low",
        "max_value": "full",
        "min_elevation": -6.0,
        "max_elevation": 10.0,
    }


async def test_options_flow_rejects_out_of_range_interval(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    result = await _open_options(hass, aioclient_mock, config_entry)
    for bad in (14, 301):
        with pytest.raises(InvalidData):
            await hass.config_entries.options.async_configure(
                result["flow_id"], {**FULL_OPTIONS, "scan_interval": bad}
            )


async def test_options_flow_rejects_min_value_above_max_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    result = await _open_options(hass, aioclient_mock, config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**FULL_OPTIONS, "min_value": "full", "max_value": "low"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"min_value": "value_range"}


async def test_options_flow_allows_equal_min_and_max_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    result = await _open_options(hass, aioclient_mock, config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**FULL_OPTIONS, "min_value": "medium", "max_value": "medium"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_rejects_min_elevation_not_below_max(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    result = await _open_options(hass, aioclient_mock, config_entry)
    for low, high in ((10.0, 10.0), (12.0, 5.0)):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**FULL_OPTIONS, "min_elevation": low, "max_elevation": high}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"min_elevation": "elevation_range"}


async def test_options_flow_never_offers_off_as_a_step(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    result = await _open_options(hass, aioclient_mock, config_entry)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {**FULL_OPTIONS, "min_value": "off"}
        )
