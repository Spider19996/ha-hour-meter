"""Custom types for hour_meter integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import HourMeterCoordinator


type HourMeterConfigEntry = ConfigEntry[HourMeterData]


@dataclass
class HourMeterData:
    """Data for the Hour Meter integration."""

    coordinator: HourMeterCoordinator
