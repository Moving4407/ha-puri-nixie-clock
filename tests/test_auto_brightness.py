"""Tests for automatic brightness: triggers, timer and storage."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import FakeClock, entity_id, service, setup_integration


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    day: int = 126,
    night: int = 126,
) -> FakeClock:
    clock = FakeClock(aioclient_mock, brightnessday=day, brightnessnight=night)
    await setup_integration(hass, config_entry)
    return clock


async def _advance(hass: HomeAssistant, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)


async def _enable(hass: HomeAssistant) -> None:
    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "auto_brightness"))


async def test_auto_switch_is_off_by_default(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry)

    assert hass.states.get(entity_id(hass, "switch", "auto_brightness")).state == STATE_OFF
    assert clock.writes == []


async def test_turning_on_adjusts_both_values_once(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 1)
    sun_elevation.value = 10.0  # 256

    await _enable(hass)

    assert hass.states.get(entity_id(hass, "switch", "auto_brightness")).state == STATE_ON
    # The same value for both, because the integration cannot tell which one is in use.
    assert clock.writes == [("brightnessday", 256), ("brightnessnight", 256)]


async def test_no_write_when_target_equals_current_values(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 126)
    sun_elevation.value = 0.0  # 126

    await _enable(hass)

    assert clock.writes == []


async def test_only_the_differing_value_is_written(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 71)
    sun_elevation.value = 0.0  # 126

    await _enable(hass)

    assert clock.writes == [("brightnessnight", 126)]


async def test_no_write_while_display_is_off(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    freezer,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 1, 1)
    await _enable(hass)
    await _advance(hass, freezer, 31)

    assert clock.writes == []
    assert hass.states.get(entity_id(hass, "switch", "display")).state == STATE_OFF


async def test_no_write_without_sun_elevation(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    freezer,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 201)
    sun_elevation.value = None
    await _enable(hass)
    await _advance(hass, freezer, 31)

    assert clock.writes == []


async def test_at_most_one_round_per_30_minutes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    freezer,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 256, 256)
    sun_elevation.value = 10.0
    await _enable(hass)
    assert clock.writes == []

    sun_elevation.value = -6.0  # target 6
    await _advance(hass, freezer, 29)
    assert clock.writes == []

    await _advance(hass, freezer, 1)
    assert clock.writes == [("brightnessday", 6), ("brightnessnight", 6)]

    sun_elevation.value = 10.0
    await _advance(hass, freezer, 1)
    await _advance(hass, freezer, 28)
    assert len(clock.writes) == 2

    await _advance(hass, freezer, 1)
    assert clock.writes[2:] == [("brightnessday", 256), ("brightnessnight", 256)]


async def test_manual_choice_is_overwritten_at_the_next_tick(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    freezer,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 126)
    sun_elevation.value = 0.0  # 126
    await _enable(hass)

    await service(hass)(
        "select", "select_option", entity_id(hass, "select", "brightness_day"), option="full"
    )
    assert clock.values["brightnessday"] == 256
    clock.writes.clear()

    await _advance(hass, freezer, 30)

    assert clock.writes == [("brightnessday", 126)]


async def test_turning_off_stops_the_timer(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    freezer,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 126)
    sun_elevation.value = 0.0
    await _enable(hass)
    await service(hass)("switch", "turn_off", entity_id(hass, "switch", "auto_brightness"))

    sun_elevation.value = 10.0
    await _advance(hass, freezer, 60)

    assert clock.writes == []


async def test_custom_options_are_used(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            "min_value": "low",
            "max_value": "high",
            "min_elevation": 0.0,
            "max_elevation": 20.0,
        },
    )
    clock = await _setup(hass, aioclient_mock, config_entry, 256, 256)
    call = service(hass)

    sun_elevation.value = -5.0  # below the range: darkest allowed step
    await _enable(hass)
    assert clock.values["brightnessday"] == 71

    await call("switch", "turn_off", entity_id(hass, "switch", "auto_brightness"))
    sun_elevation.value = 40.0  # above the range: brightest allowed step
    await _enable(hass)
    assert clock.values["brightnessday"] == 201


async def test_a_failing_write_does_not_break_the_timer(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    freezer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 126)
    sun_elevation.value = 0.0
    await _enable(hass)

    sun_elevation.value = 10.0
    clock.html_on_write = True
    await _advance(hass, freezer, 30)
    assert "Automatic brightness could not adjust the clock" in caplog.text

    clock.html_on_write = False
    await _advance(hass, freezer, 30)
    assert clock.values["brightnessday"] == 256


async def test_enabled_state_is_stored_and_nothing_is_written_after_restart(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
    hass_storage: dict,
    freezer,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 126)
    sun_elevation.value = 0.0
    await _enable(hass)
    stored = hass_storage[f"puri_nixie_clock.{config_entry.entry_id}"]["data"]
    assert stored["auto_enabled"] is True

    sun_elevation.value = 10.0
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "switch", "auto_brightness")).state == STATE_ON
    assert clock.writes == []  # never write on startup

    await _advance(hass, freezer, 30)
    assert clock.values["brightnessday"] == 256
