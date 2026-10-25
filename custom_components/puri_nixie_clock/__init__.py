"""The Puri Nixie Clock integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import PuriClockClient
from .const import DOMAIN
from .controller import STORAGE_VERSION, PuriController
from .coordinator import PuriConfigEntry, PuriCoordinator, PuriRuntimeData

PLATFORMS = [Platform.SELECT, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: PuriConfigEntry) -> bool:
    """Set up a clock from a config entry. Reads only; nothing is written to the clock."""
    client = PuriClockClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT]
    )
    coordinator = PuriCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    controller = PuriController(hass, entry, coordinator)
    await controller.async_setup()
    entry.async_on_unload(controller.async_unload)
    entry.runtime_data = PuriRuntimeData(coordinator, controller)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PuriConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: PuriConfigEntry) -> None:
    """Delete the stored state of a removed config entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
