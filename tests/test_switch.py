"""Tests for the display switch and the brightness selects."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import FakeClock, entity_id, service, setup_integration


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    day: int,
    night: int,
) -> FakeClock:
    clock = FakeClock(aioclient_mock, brightnessday=day, brightnessnight=night)
    await setup_integration(hass, config_entry)
    return clock


@pytest.mark.parametrize(
    ("day", "night", "expected"),
    [(1, 1, STATE_OFF), (1, 6, STATE_ON), (6, 1, STATE_ON), (201, 126, STATE_ON)],
)
async def test_display_state_is_derived_from_both_values(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    day: int,
    night: int,
    expected: str,
) -> None:
    await _setup(hass, aioclient_mock, config_entry, day, night)

    assert hass.states.get(entity_id(hass, "switch", "display")).state == expected


async def test_nothing_is_written_at_startup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)

    assert clock.writes == []


async def test_turn_off_writes_one_and_remembers_values(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    hass_storage: dict,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)
    switch = entity_id(hass, "switch", "display")

    await service(hass)("switch", "turn_off", switch)

    assert clock.writes == [("brightnessday", 1), ("brightnessnight", 1)]
    assert hass.states.get(switch).state == STATE_OFF
    stored = hass_storage[f"puri_nixie_clock.{config_entry.entry_id}"]["data"]
    assert stored["last_on"] == {"day": 201, "night": 126}


async def test_turn_off_when_already_off_keeps_remembered_values(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    hass_storage: dict,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)
    switch = entity_id(hass, "switch", "display")
    await service(hass)("switch", "turn_off", switch)
    clock.writes.clear()

    await service(hass)("switch", "turn_off", switch)

    assert clock.writes == []
    stored = hass_storage[f"puri_nixie_clock.{config_entry.entry_id}"]["data"]
    assert stored["last_on"] == {"day": 201, "night": 126}


async def test_turn_on_restores_remembered_values(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 126, 71)
    switch = entity_id(hass, "switch", "display")
    await service(hass)("switch", "turn_off", switch)
    clock.writes.clear()

    await service(hass)("switch", "turn_on", switch)

    assert clock.writes == [("brightnessday", 126), ("brightnessnight", 71)]
    assert hass.states.get(switch).state == STATE_ON


async def test_turn_on_without_memory_uses_option_defaults(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 1, 1)

    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "display"))

    assert clock.writes == [("brightnessday", 256), ("brightnessnight", 126)]


async def test_turn_on_without_memory_uses_configured_defaults(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={"display_on_day": "low", "display_on_night": "very_low"}
    )
    clock = await _setup(hass, aioclient_mock, config_entry, 1, 1)

    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "display"))

    assert clock.writes == [("brightnessday", 71), ("brightnessnight", 6)]


async def test_turn_on_writes_only_values_that_differ(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """From (1, 126) with defaults (256, 126) only the day value needs writing."""
    clock = await _setup(hass, aioclient_mock, config_entry, 1, 126)
    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "display"))
    # (1, 126) already counts as on, so turn_on re-applies the defaults.

    assert clock.writes == [("brightnessday", 256)]


async def test_turn_on_uses_automatic_target_when_automatic_brightness_is_on(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 1, 1)
    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "auto_brightness"))
    assert clock.writes == []  # display is off: automatic brightness leaves it alone

    sun_elevation.value = 2.0  # target 126
    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "display"))

    assert clock.writes == [("brightnessday", 126), ("brightnessnight", 126)]


async def test_turn_on_falls_back_to_memory_without_sun_elevation(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    sun_elevation: SimpleNamespace,
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 71)
    display = entity_id(hass, "switch", "display")
    sun_elevation.value = None
    await service(hass)("switch", "turn_on", entity_id(hass, "switch", "auto_brightness"))
    await service(hass)("switch", "turn_off", display)
    clock.writes.clear()

    await service(hass)("switch", "turn_on", display)

    assert clock.writes == [("brightnessday", 201), ("brightnessnight", 71)]


async def test_remembered_values_survive_a_restart(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 71)
    display = entity_id(hass, "switch", "display")
    await service(hass)("switch", "turn_off", display)

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    clock.writes.clear()
    await service(hass)("switch", "turn_on", display)

    assert clock.writes == [("brightnessday", 201), ("brightnessnight", 71)]


async def test_write_failure_raises_and_keeps_state(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)
    switch = entity_id(hass, "switch", "display")
    clock.html_on_write = True

    with pytest.raises(HomeAssistantError):
        await service(hass)("switch", "turn_off", switch)

    assert hass.states.get(switch).state == STATE_ON
    assert clock.values["brightnessday"] == 201


async def test_write_the_clock_did_not_apply_raises_and_shows_the_real_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)
    clock.ignore_writes = True
    select = entity_id(hass, "select", "brightness_day")

    with pytest.raises(HomeAssistantError):
        await service(hass)("select", "select_option", select, option="low")

    assert hass.states.get(select).state == "high"


async def test_select_sets_one_value(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)

    await service(hass)(
        "select", "select_option", entity_id(hass, "select", "brightness_night"), option="low"
    )

    assert clock.writes == [("brightnessnight", 71)]
    assert hass.states.get(entity_id(hass, "select", "brightness_night")).state == "low"
    assert hass.states.get(entity_id(hass, "select", "brightness_day")).state == "high"


async def test_selecting_off_for_one_value_keeps_display_on(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    clock = await _setup(hass, aioclient_mock, config_entry, 201, 126)

    await service(hass)(
        "select", "select_option", entity_id(hass, "select", "brightness_night"), option="off"
    )

    assert clock.writes == [("brightnessnight", 1)]
    assert hass.states.get(entity_id(hass, "switch", "display")).state == STATE_ON


async def test_selecting_off_for_both_values_turns_display_off(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, aioclient_mock, config_entry, 201, 126)
    call = service(hass)

    await call("select", "select_option", entity_id(hass, "select", "brightness_day"), option="off")
    await call(
        "select", "select_option", entity_id(hass, "select", "brightness_night"), option="off"
    )

    assert hass.states.get(entity_id(hass, "switch", "display")).state == STATE_OFF


@pytest.mark.parametrize(
    ("value", "option"),
    [(1, "off"), (6, "very_low"), (71, "low"), (126, "medium"), (201, "high"), (256, "full")],
)
async def test_select_shows_each_step(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    value: int,
    option: str,
) -> None:
    await _setup(hass, aioclient_mock, config_entry, value, 126)

    assert hass.states.get(entity_id(hass, "select", "brightness_day")).state == option


async def test_select_shows_unknown_for_a_value_that_is_not_a_step(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, aioclient_mock, config_entry, 50, 126)

    assert hass.states.get(entity_id(hass, "select", "brightness_day")).state == STATE_UNKNOWN
