"""Tests for the automatic brightness function and the sun elevation lookup."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.puri_nixie_clock.brightness import auto_target
from custom_components.puri_nixie_clock.controller import get_sun_elevation


@pytest.mark.parametrize(
    ("elevation", "expected"),
    [
        (-90, 6),
        (-10, 6),
        (-6, 6),
        (-2, 71),  # raw 68.5
        (0, 126),  # raw 99.75
        (2, 126),  # raw 131
        (6, 201),  # raw 193.5
        (10, 256),
        (45, 256),
    ],
)
def test_auto_target_reference_table(elevation: float, expected: int) -> None:
    """The reference results of SPEC.md section 4.4."""
    assert auto_target(elevation) == expected


def test_auto_target_tie_takes_the_lower_step() -> None:
    # 6..256 over 0..250 degrees: raw = 6 + elevation. 38.5 lies midway between 6 and 71.
    assert auto_target(32.5, lo_elev=0, hi_elev=250) == 6
    assert auto_target(32.6, lo_elev=0, hi_elev=250) == 71


def test_auto_target_custom_options() -> None:
    assert auto_target(-5, lo_elev=0, hi_elev=20, lo_val=71, hi_val=201) == 71
    assert auto_target(25, lo_elev=0, hi_elev=20, lo_val=71, hi_val=201) == 201
    assert auto_target(10, lo_elev=0, hi_elev=20, lo_val=71, hi_val=201) == 126


def test_auto_target_never_returns_off() -> None:
    assert all(auto_target(elevation) > 1 for elevation in range(-90, 91))


def test_auto_target_single_step_range() -> None:
    assert auto_target(-50, lo_val=126, hi_val=126) == 126
    assert auto_target(50, lo_val=126, hi_val=126) == 126


async def test_sun_elevation_is_read_from_sun_state(hass: HomeAssistant) -> None:
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 12.5})
    assert get_sun_elevation(hass) == 12.5
    hass.states.async_set("sun.sun", "below_horizon", {"elevation": -3})
    assert get_sun_elevation(hass) == -3.0


@pytest.mark.parametrize(
    "attributes", [{}, {"elevation": None}, {"elevation": "x"}, {"elevation": True}]
)
async def test_sun_elevation_unavailable(hass: HomeAssistant, attributes: dict) -> None:
    hass.states.async_set("sun.sun", "unavailable", attributes)
    assert get_sun_elevation(hass) is None


async def test_sun_elevation_without_sun_entity(hass: HomeAssistant) -> None:
    assert get_sun_elevation(hass) is None
