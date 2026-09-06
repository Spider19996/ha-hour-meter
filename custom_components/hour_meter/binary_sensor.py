"""Binary sensor platform for hour_meter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import DOMAIN
from .entity import HourMeterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HourMeterCoordinator
    from .data import HourMeterConfigEntry

TRACKING_DESCRIPTION = BinarySensorEntityDescription(
    key="aktiv",
    translation_key="aktiv",
    icon="mdi:play-circle",
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: HourMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform from a config entry."""
    coordinator: HourMeterCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        [HourMeterTrackingBinarySensor(coordinator, entry, TRACKING_DESCRIPTION)]
    )


class HourMeterTrackingBinarySensor(HourMeterEntity, BinarySensorEntity):
    """Hour Meter Tracking Status Binary Sensor class."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: HourMeterCoordinator,
        entry: HourMeterConfigEntry,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = entity_description
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{entity_description.key}"

    @property
    def is_on(self) -> bool:
        """Return true if tracking is active."""
        return self.coordinator.is_tracking

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend."""
        if self.is_on:
            return "mdi:play-circle"
        return "mdi:stop-circle"
