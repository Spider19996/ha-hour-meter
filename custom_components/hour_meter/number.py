"""Number platform for hour_meter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfTime

from .const import DOMAIN
from .entity import HourMeterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HourMeterCoordinator
    from .data import HourMeterConfigEntry

NUMBER_DESCRIPTION = NumberEntityDescription(
    key="stunden_eingabe",
    translation_key="stunden_eingabe",
    icon="mdi:pencil",
    native_unit_of_measurement=UnitOfTime.HOURS,
    native_min_value=0,
    native_max_value=9999999,
    native_step=0.1,
    device_class=NumberDeviceClass.DURATION,
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: HourMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform from a config entry."""
    coordinator: HourMeterCoordinator = entry.runtime_data.coordinator
    async_add_entities([HourMeterNumber(coordinator, entry, NUMBER_DESCRIPTION)])


class HourMeterNumber(HourMeterEntity, NumberEntity):
    """Hour Meter Number class."""

    entity_description: NumberEntityDescription

    def __init__(
        self,
        coordinator: HourMeterCoordinator,
        entry: HourMeterConfigEntry,
        entity_description: NumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, entry)
        self.entity_description = entity_description
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{entity_description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.coordinator.data

    async def async_set_native_value(self, value: float) -> None:
        """Set the runtime hours value."""
        await self.coordinator.async_set_manual(value)
