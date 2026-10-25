"""Brightness selects for the Puri Nixie Clock."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BRIGHTNESS_OPTIONS, PARAM_BRIGHTNESS_DAY, PARAM_BRIGHTNESS_NIGHT
from .controller import PuriController
from .coordinator import PuriConfigEntry, PuriCoordinator
from .entity import PuriEntity

_KEY_BY_VALUE = {value: key for key, value in BRIGHTNESS_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: PuriConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the selects."""
    runtime = entry.runtime_data
    async_add_entities(
        [
            PuriBrightnessSelect(
                runtime.coordinator, runtime.controller, "brightness_day", PARAM_BRIGHTNESS_DAY
            ),
            PuriBrightnessSelect(
                runtime.coordinator, runtime.controller, "brightness_night", PARAM_BRIGHTNESS_NIGHT
            ),
        ]
    )


class PuriBrightnessSelect(PuriEntity, SelectEntity):
    """Day or night brightness, one of the six steps the clock knows."""

    def __init__(
        self, coordinator: PuriCoordinator, controller: PuriController, key: str, param: str
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, key)
        self._attr_options = list(BRIGHTNESS_OPTIONS)
        self._controller = controller
        self._param = param

    @property
    def current_option(self) -> str | None:
        """Return the current step, or None for a value that is not a step."""
        data = self.coordinator.data
        value = (
            data.brightness_day if self._param == PARAM_BRIGHTNESS_DAY else data.brightness_night
        )
        return _KEY_BY_VALUE.get(value)

    async def async_select_option(self, option: str) -> None:
        """Set the brightness. Choosing "off" for one value does not switch the display off."""
        await self._controller.async_set_brightness(self._param, BRIGHTNESS_OPTIONS[option])
