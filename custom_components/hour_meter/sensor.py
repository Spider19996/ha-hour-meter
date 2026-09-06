"""Sensor platform for hour_meter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)

from .const import DOMAIN
from .entity import HourMeterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HourMeterCoordinator
    from .data import HourMeterConfigEntry

SENSOR_DESCRIPTION = SensorEntityDescription(
    key="betriebsstunden",
    translation_key="betriebsstunden",
    icon="mdi:timer-sand",
    native_unit_of_measurement="h",
    state_class=SensorStateClass.TOTAL,
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: HourMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform from a config entry."""
    coordinator: HourMeterCoordinator = entry.runtime_data.coordinator
    async_add_entities([HourMeterSensor(coordinator, entry, SENSOR_DESCRIPTION)])


class HourMeterSensor(HourMeterEntity, SensorEntity):
    """Hour Meter Sensor class."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: HourMeterCoordinator,
        entry: HourMeterConfigEntry,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = entity_description
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{entity_description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        return self.coordinator.data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the most recent CSV entries for dashboard display."""
        return {"csv_data": self.coordinator.csv_data}

    @property
    def icon(self) -> str:
        """Return the icon based on tracking status."""
        if self.coordinator.is_tracking:
            return "mdi:timer-sand"
        return "mdi:timer-sand-complete"
