"""Data update coordinator for the Puri Nixie Clock."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PuriClockClient, PuriClockError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PARAM_BRIGHTNESS_DAY,
    PARAM_BRIGHTNESS_NIGHT,
    PARAM_DISPLAYED_VALUE,
    PARAM_RSSI,
)

if TYPE_CHECKING:
    from .controller import PuriController

_LOGGER = logging.getLogger(__name__)

type PuriConfigEntry = ConfigEntry[PuriRuntimeData]


@dataclass(frozen=True)
class PuriData:
    """One snapshot of the clock."""

    brightness_day: int
    brightness_night: int
    displayed_value: int
    rssi: int


@dataclass
class PuriRuntimeData:
    """What a loaded config entry holds."""

    coordinator: PuriCoordinator
    controller: PuriController


class PuriCoordinator(DataUpdateCoordinator[PuriData]):
    """Poll the clock, one request at a time.

    Home Assistant logs the first failed update and the recovery once each, which gives
    one log line per outage.
    """

    config_entry: PuriConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: PuriConfigEntry, client: PuriClockClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client

    async def _async_update_data(self) -> PuriData:
        """Read the clock."""
        try:
            return PuriData(
                brightness_day=await self.client.get(PARAM_BRIGHTNESS_DAY),
                brightness_night=await self.client.get(PARAM_BRIGHTNESS_NIGHT),
                displayed_value=await self.client.get(PARAM_DISPLAYED_VALUE),
                rssi=await self.client.get(PARAM_RSSI),
            )
        except PuriClockError as err:
            raise UpdateFailed(f"Error communicating with the clock: {err}") from err
