"""Diagnostics support for the hour_meter integration.

For more details about this integration, please refer to
https://github.com/spider19996/ha-generator-hours-tracker
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .data import HourMeterConfigEntry

# Redact file paths from diagnostics (can contain sensitive info)
REDACT = {"csv_path", "startzeit_path"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: HourMeterConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(entry.data, REDACT),
            "options": async_redact_data(entry.options, REDACT),
        },
        "state": {
            "total_hours": coordinator.data,
            "is_tracking": coordinator.is_tracking,
            "latency_seconds": coordinator.latency_seconds,
            "merge_time_seconds": coordinator.merge_time_seconds,
            "csv_path": str(coordinator.csv_path),
            "startzeit_path": str(coordinator.startzeit_path),
            "last_csv_entries": coordinator.csv_data[-5:],
        },
    }
