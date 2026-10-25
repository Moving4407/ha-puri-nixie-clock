"""Base entity for the Puri Nixie Clock."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, PRODUCT_MODELS
from .coordinator import PuriCoordinator


class PuriEntity(CoordinatorEntity[PuriCoordinator]):
    """An entity of one clock; the serial number identifies the device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PuriCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        serial = entry.unique_id
        assert serial is not None
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            model=PRODUCT_MODELS.get(entry.data["product_id"]),
            name="Puri Nixie Clock",
        )
