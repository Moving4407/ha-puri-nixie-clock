"""Sensors for the Puri Nixie Clock."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PuriConfigEntry, PuriData
from .entity import PuriEntity


@dataclass(frozen=True, kw_only=True)
class PuriSensorDescription(SensorEntityDescription):
    """Describe a clock sensor."""

    value_fn: Callable[[PuriData], int]


SENSORS = (
    PuriSensorDescription(
        key="displayed_value",
        translation_key="displayed_value",
        value_fn=lambda data: data.displayed_value,
    ),
    PuriSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PuriConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(PuriSensor(coordinator, description) for description in SENSORS)


class PuriSensor(PuriEntity, SensorEntity):
    """A sensor reading from the coordinator snapshot."""

    entity_description: PuriSensorDescription

    def __init__(self, coordinator, description: PuriSensorDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
