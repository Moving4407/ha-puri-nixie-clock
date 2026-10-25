"""Switches for the Puri Nixie Clock: the display and automatic brightness."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .controller import PuriController
from .coordinator import PuriConfigEntry, PuriCoordinator
from .entity import PuriEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PuriConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the switches."""
    runtime = entry.runtime_data
    async_add_entities(
        [
            PuriDisplaySwitch(runtime.coordinator, runtime.controller),
            PuriAutoBrightnessSwitch(runtime.coordinator, runtime.controller),
        ]
    )


class PuriDisplaySwitch(PuriEntity, SwitchEntity):
    """Switch the tubes on and off; on unless both brightness values are 1."""

    def __init__(self, coordinator: PuriCoordinator, controller: PuriController) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "display")
        self._controller = controller

    @property
    def is_on(self) -> bool:
        """Return whether the display is on."""
        return self._controller.display_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the display on."""
        await self._controller.async_turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the display off."""
        await self._controller.async_turn_off()


class PuriAutoBrightnessSwitch(PuriEntity, SwitchEntity):
    """Let the brightness follow the sun."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PuriCoordinator, controller: PuriController) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "auto_brightness")
        self._controller = controller

    @property
    def is_on(self) -> bool:
        """Return whether automatic brightness is on."""
        return self._controller.auto_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn automatic brightness on."""
        await self._controller.async_set_auto(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn automatic brightness off."""
        await self._controller.async_set_auto(False)
