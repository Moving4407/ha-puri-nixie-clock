"""Display switch and automatic brightness logic (SPEC.md sections 4.3, 4.4 and 4.9)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from typing import TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .api import PuriClockError
from .brightness import auto_target
from .const import (
    AUTO_BRIGHTNESS_INTERVAL,
    BRIGHTNESS_OFF,
    BRIGHTNESS_OPTIONS,
    CONF_DISPLAY_ON_DAY,
    CONF_DISPLAY_ON_NIGHT,
    CONF_MAX_ELEVATION,
    CONF_MAX_VALUE,
    CONF_MIN_ELEVATION,
    CONF_MIN_VALUE,
    DEFAULT_DISPLAY_ON_DAY,
    DEFAULT_DISPLAY_ON_NIGHT,
    DEFAULT_MAX_ELEVATION,
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_MIN_VALUE,
    DOMAIN,
    PARAM_BRIGHTNESS_DAY,
    PARAM_BRIGHTNESS_NIGHT,
    SUN_ENTITY_ID,
)
from .coordinator import PuriConfigEntry, PuriCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


class LastOn(TypedDict):
    """The brightness values from before the display was switched off."""

    day: int
    night: int


class StoredState(TypedDict, total=False):
    """What is kept between restarts."""

    last_on: LastOn
    auto_enabled: bool


def get_sun_elevation(hass: HomeAssistant) -> float | None:
    """Return the solar elevation in degrees, or None when it is not available."""
    state = hass.states.get(SUN_ENTITY_ID)
    if state is None:
        return None
    elevation = state.attributes.get("elevation")
    if isinstance(elevation, bool) or not isinstance(elevation, int | float):
        return None
    return float(elevation)


class PuriController:
    """Switch the display and follow the sun. The only code that writes to the clock."""

    def __init__(
        self, hass: HomeAssistant, entry: PuriConfigEntry, coordinator: PuriCoordinator
    ) -> None:
        """Initialize the controller."""
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._store: Store[StoredState] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._lock = asyncio.Lock()
        self._unsub_timer: Callable[[], None] | None = None
        self._last_on: LastOn | None = None
        self.auto_enabled = False

    async def async_setup(self) -> None:
        """Load the stored state. Nothing is written to the clock."""
        stored = await self._store.async_load() or {}
        self._last_on = stored.get("last_on")
        self.auto_enabled = bool(stored.get("auto_enabled", False))
        if self.auto_enabled:
            self._start_timer()

    @callback
    def async_unload(self) -> None:
        """Stop the automatic brightness timer."""
        self._stop_timer()

    async def async_remove_storage(self) -> None:
        """Delete the stored state when the config entry is removed."""
        await self._store.async_remove()

    # State -------------------------------------------------------------------

    @property
    def display_on(self) -> bool:
        """The display is on unless both brightness values are 1."""
        data = self._coordinator.data
        return data.brightness_day > BRIGHTNESS_OFF or data.brightness_night > BRIGHTNESS_OFF

    def _option_value(self, key: str, default: str) -> int:
        return BRIGHTNESS_OPTIONS[self._entry.options.get(key, default)]

    # Display switch ----------------------------------------------------------

    async def async_turn_off(self) -> None:
        """Remember the brightness and turn the tubes dark."""
        async with self._lock:
            data = self._coordinator.data
            if self.display_on:
                self._last_on = {"day": data.brightness_day, "night": data.brightness_night}
                await self._async_save()
            await self._async_write_brightness(BRIGHTNESS_OFF, BRIGHTNESS_OFF)

    async def async_turn_on(self) -> None:
        """Turn the tubes on at the automatic, the remembered or the default brightness."""
        async with self._lock:
            target = self._auto_brightness() if self.auto_enabled else None
            if target is not None:
                day = night = target
            elif self._last_on is not None:
                day, night = self._last_on["day"], self._last_on["night"]
            else:
                day = self._option_value(CONF_DISPLAY_ON_DAY, DEFAULT_DISPLAY_ON_DAY)
                night = self._option_value(CONF_DISPLAY_ON_NIGHT, DEFAULT_DISPLAY_ON_NIGHT)
            await self._async_write_brightness(day, night)

    async def async_set_brightness(self, param: str, value: int) -> None:
        """Set one brightness value, for the select entities."""
        async with self._lock:
            await self._async_write_brightness(
                value if param == PARAM_BRIGHTNESS_DAY else None,
                value if param == PARAM_BRIGHTNESS_NIGHT else None,
            )

    # Automatic brightness ----------------------------------------------------

    async def async_set_auto(self, enabled: bool) -> None:
        """Switch automatic brightness on or off; switching on adjusts once at once."""
        async with self._lock:
            self.auto_enabled = enabled
            await self._async_save()
            if enabled:
                self._start_timer()
                self._coordinator.async_update_listeners()
                await self._async_adjust()
            else:
                self._stop_timer()
                self._coordinator.async_update_listeners()

    def _auto_brightness(self) -> int | None:
        """The brightness for the current sun elevation, or None without one."""
        elevation = get_sun_elevation(self._hass)
        if elevation is None:
            return None
        options = self._entry.options
        return auto_target(
            elevation,
            lo_elev=options.get(CONF_MIN_ELEVATION, DEFAULT_MIN_ELEVATION),
            hi_elev=options.get(CONF_MAX_ELEVATION, DEFAULT_MAX_ELEVATION),
            lo_val=self._option_value(CONF_MIN_VALUE, DEFAULT_MIN_VALUE),
            hi_val=self._option_value(CONF_MAX_VALUE, DEFAULT_MAX_VALUE),
        )

    async def _async_adjust(self) -> None:
        """One adjustment round. Does nothing while the display is off."""
        if not self.display_on:
            return
        target = self._auto_brightness()
        if target is None:
            return
        await self._async_write_brightness(target, target)

    def _start_timer(self) -> None:
        if self._unsub_timer is None:
            self._unsub_timer = async_track_time_interval(
                self._hass,
                self._async_timer_tick,
                timedelta(seconds=AUTO_BRIGHTNESS_INTERVAL),
            )

    def _stop_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    async def _async_timer_tick(self, _now: object) -> None:
        async with self._lock:
            try:
                await self._async_adjust()
            except HomeAssistantError as err:
                _LOGGER.warning("Automatic brightness could not adjust the clock: %s", err)

    # Writing -----------------------------------------------------------------

    async def _async_write_brightness(self, day: int | None, night: int | None) -> None:
        """Write the values that differ from the current ones. The lock must be held."""
        data = self._coordinator.data
        if day is not None and day != data.brightness_day:
            await self._async_write(PARAM_BRIGHTNESS_DAY, day)
        if night is not None and night != self._coordinator.data.brightness_night:
            await self._async_write(PARAM_BRIGHTNESS_NIGHT, night)

    async def _async_write(self, param: str, value: int) -> None:
        """Write one parameter; the coordinator data changes only with the value read back."""
        try:
            read_back = await self._coordinator.client.set(param, value)
        except PuriClockError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        field = "brightness_day" if param == PARAM_BRIGHTNESS_DAY else "brightness_night"
        self._coordinator.async_set_updated_data(
            replace(self._coordinator.data, **{field: read_back})
        )
        if read_back != value:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_not_applied",
                translation_placeholders={"param": param, "value": str(value)},
            )

    async def _async_save(self) -> None:
        state: StoredState = {"auto_enabled": self.auto_enabled}
        if self._last_on is not None:
            state["last_on"] = self._last_on
        await self._store.async_save(state)
