"""Base entity for hour_meter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import HourMeterCoordinator

if TYPE_CHECKING:
    from .data import HourMeterConfigEntry


class HourMeterEntity(CoordinatorEntity[HourMeterCoordinator]):
    """Base entity for Hour Meter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HourMeterCoordinator,
        entry: HourMeterConfigEntry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        # Unique per config entry so multiple devices are supported
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_device"
        self._attr_device_info = DeviceInfo(
            # Unique device identifier per device (config entry)
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or "Hour Meter",
            manufacturer=MANUFACTURER,
            model="Runtime Tracker",
        )
