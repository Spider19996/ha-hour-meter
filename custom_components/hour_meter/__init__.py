"""
Custom integration for tracking device operating hours.

For more details about this integration, please refer to
https://github.com/spider19996/ha-generator-hours-tracker
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_BINARY_SENSOR,
    CONF_CSV_PATH,
    CONF_INVERT,
    CONF_LATENCY,
    CONF_MERGE_TIME,
    CONF_STARTZEIT_PATH,
    DEFAULT_CSV_PATH,
    DEFAULT_LATENCY_SECONDS,
    DEFAULT_MERGE_TIME_SECONDS,
    DEFAULT_STARTZEIT_PATH,
    DOMAIN,
    LOGGER,
)
from .coordinator import HourMeterCoordinator
from .data import HourMeterData

if TYPE_CHECKING:
    from .data import HourMeterConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
]

# Service schemas
SERVICE_START = "start"
SERVICE_STOP = "stop"
SERVICE_MANUAL = "manual"

# Optional field to select a specific device when multiple are configured
SERVICE_DEVICE_FIELD = "device"

SERVICE_START_SCHEMA = vol.Schema({vol.Optional(SERVICE_DEVICE_FIELD): vol.Coerce(str)})
SERVICE_STOP_SCHEMA = vol.Schema({vol.Optional(SERVICE_DEVICE_FIELD): vol.Coerce(str)})
SERVICE_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required("value"): vol.Coerce(float),
        vol.Optional(SERVICE_DEVICE_FIELD): vol.Coerce(str),
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HourMeterConfigEntry,
) -> bool:
    """Set up hour_meter from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get configuration from entry (options override data after options flow)
    config = {**entry.data, **entry.options}
    csv_path = config.get(CONF_CSV_PATH, DEFAULT_CSV_PATH)
    startzeit_path = config.get(CONF_STARTZEIT_PATH, DEFAULT_STARTZEIT_PATH)
    binary_sensor_entity = config.get(CONF_BINARY_SENSOR, "")
    invert = config.get(CONF_INVERT, False)
    latency_seconds = config.get(CONF_LATENCY, DEFAULT_LATENCY_SECONDS)
    merge_time_seconds = config.get(CONF_MERGE_TIME, DEFAULT_MERGE_TIME_SECONDS)

    # Create coordinator
    coordinator = HourMeterCoordinator(
        hass=hass,
        csv_path=csv_path,
        startzeit_path=startzeit_path,
        latency_seconds=latency_seconds,
        merge_time_seconds=merge_time_seconds,
    )

    # Ensure required directories and files exist (non-blocking)
    await coordinator.async_ensure_directories_and_files()

    # Store data in entry.runtime_data
    entry.runtime_data = HourMeterData(
        coordinator=coordinator,
    )

    # Perform initial data fetch
    await coordinator.async_config_entry_first_refresh()

    # Initialize the in-memory tracking flag from the start time marker file
    await coordinator.async_init_tracking_state()

    # Handle HA restart - check for active tracking
    await coordinator.async_handle_ha_restart(binary_sensor_entity, invert)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (shared across all entries of this integration)
    if not hass.services.has_service(DOMAIN, SERVICE_START):
        await _async_register_services(hass)

    # Remove the services again once this was the last loaded entry
    entry.async_on_unload(
        partial(_async_unregister_services_if_last, hass, entry.entry_id)
    )

    # Set up binary sensor tracking if configured
    if binary_sensor_entity:
        await _async_setup_binary_sensor_tracking(
            hass, entry, coordinator, binary_sensor_entity, invert
        )

    # Reload integration when options are changed in the UI
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _async_unregister_services_if_last(hass: HomeAssistant, entry_id: str) -> None:
    """Unregister the integration services when no other entry is loaded."""
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry_id and other.state == ConfigEntryState.LOADED:
            return
    for service_name in (SERVICE_START, SERVICE_STOP, SERVICE_MANUAL):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)


async def _async_update_listener(
    hass: HomeAssistant,
    entry: HourMeterConfigEntry,
) -> None:
    """Handle options update."""
    LOGGER.info("Options updated for %s, reloading integration", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: HourMeterConfigEntry,
) -> bool:
    """Unload a config entry."""
    # Entity-tracking subscriptions and the latency timer are cleaned up via
    # entry.async_on_unload callbacks registered during setup.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant,
    entry: HourMeterConfigEntry,
) -> None:
    """Remove a config entry and clean up the empty start time marker file."""
    startzeit_path = entry.options.get(
        CONF_STARTZEIT_PATH,
        entry.data.get(CONF_STARTZEIT_PATH, DEFAULT_STARTZEIT_PATH),
    )
    csv_path = entry.options.get(
        CONF_CSV_PATH, entry.data.get(CONF_CSV_PATH, DEFAULT_CSV_PATH)
    )
    try:
        path = Path(startzeit_path)
        if path.exists() and path.stat().st_size == 0:
            await asyncio.to_thread(path.unlink)
            LOGGER.info("Removed empty start time marker file: %s", startzeit_path)
        else:
            LOGGER.info(
                "Keeping start time file %s (non-empty or missing)",
                startzeit_path,
            )
    except OSError as err:
        LOGGER.warning("Could not remove start time file %s: %s", startzeit_path, err)

    LOGGER.info("CSV history file %s is intentionally preserved", csv_path)


def _get_coordinator(
    hass: HomeAssistant,
    call: ServiceCall,
) -> HourMeterCoordinator | None:
    """Resolve the coordinator for a service call.

    If the ``device`` field is provided, the coordinator for that device
    (matched by config entry id or title) is returned. Otherwise a single
    configured device is used.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        LOGGER.error("No %s entries configured", DOMAIN)
        return None

    target = call.data.get(SERVICE_DEVICE_FIELD)
    if target:
        for entry in entries:
            if entry.entry_id == target or entry.title == target:
                data = getattr(entry, "runtime_data", None)
                if data is not None:
                    return data.coordinator
        LOGGER.error("No %s device found matching '%s'", DOMAIN, target)
        return None

    if len(entries) == 1:
        data = getattr(entries[0], "runtime_data", None)
        if data is not None:
            return data.coordinator

    LOGGER.error(
        "Multiple devices are configured. Please specify the device "
        "using the '%s' field (device name or id).",
        SERVICE_DEVICE_FIELD,
    )
    return None


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register services for hour_meter."""

    async def async_start_service(call: ServiceCall) -> None:
        """Handle start service call."""
        coordinator = _get_coordinator(hass, call)
        if coordinator is None:
            return
        LOGGER.info("Starting device runtime tracking for %s", coordinator.csv_path)
        await coordinator.async_start_tracking()

    async def async_stop_service(call: ServiceCall) -> None:
        """Handle stop service call."""
        coordinator = _get_coordinator(hass, call)
        if coordinator is None:
            return
        LOGGER.info("Stopping device runtime tracking for %s", coordinator.csv_path)
        new_total = await coordinator.async_stop_tracking()
        LOGGER.info(
            "New total runtime hours for %s: %s", coordinator.csv_path, new_total
        )

    async def async_manual_service(call: ServiceCall) -> None:
        """Handle manual service call."""
        coordinator = _get_coordinator(hass, call)
        if coordinator is None:
            return
        value = call.data["value"]
        LOGGER.info(
            "Setting manual runtime hours for %s to %s",
            coordinator.csv_path,
            value,
        )
        await coordinator.async_set_manual(value)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START,
        async_start_service,
        schema=SERVICE_START_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP,
        async_stop_service,
        schema=SERVICE_STOP_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MANUAL,
        async_manual_service,
        schema=SERVICE_MANUAL_SCHEMA,
    )


async def _async_setup_binary_sensor_tracking(
    hass: HomeAssistant,
    entry,
    coordinator: HourMeterCoordinator,
    binary_sensor_entity: str,
    invert: bool = False,
) -> None:
    """Set up tracking for binary_sensor entity with latency support."""
    LOGGER.info(
        "Setting up binary sensor tracking: %s (invert: %s, latency: %ss)",
        binary_sensor_entity,
        invert,
        coordinator.latency_seconds,
    )

    latency_timer: asyncio.TimerHandle | None = None

    def _cancel_latency_timer() -> None:
        """Cancel the latency timer if running."""
        nonlocal latency_timer
        if latency_timer is not None:
            latency_timer.cancel()
            latency_timer = None

    async def _stop_with_latency() -> None:
        """Stop tracking after latency period."""
        nonlocal latency_timer
        if coordinator.latency_seconds > 0:
            LOGGER.info(
                "Starting latency timer: %ss before stopping",
                coordinator.latency_seconds,
            )
            latency_timer = hass.loop.call_later(
                coordinator.latency_seconds,
                lambda: hass.async_create_task(coordinator.async_stop_tracking()),
            )
        else:
            await coordinator.async_stop_tracking()

    async def _async_entity_changed(event: Event) -> None:
        """Handle entity state changes with latency and unavailable handling."""
        nonlocal latency_timer
        entity_id = event.data.get("entity_id", "")
        new_state = event.data.get("new_state")

        if new_state is None:
            return

        # Handle binary_sensor changes
        if entity_id == binary_sensor_entity:
            state = new_state.state

            # Ignore unavailable and unknown states
            if state in ("unavailable", "unknown"):
                LOGGER.debug("Entity %s is %s, ignoring", entity_id, state)
                # Cancel any running latency timer
                _cancel_latency_timer()
                return

            # Handle invert logic
            is_on = state == "on"
            if invert:
                is_on = not is_on

            if is_on:
                # Entity is active - cancel any pending stop and start tracking
                if latency_timer is not None:
                    LOGGER.info(
                        "Entity %s is active again, cancelling latency timer", entity_id
                    )
                    _cancel_latency_timer()

                LOGGER.info(
                    "Entity %s is active (invert=%s), starting tracking",
                    entity_id,
                    invert,
                )
                await coordinator.async_start_tracking()
            else:
                # Entity is inactive - start latency timer or stop immediately
                LOGGER.info(
                    "Entity %s is inactive (invert=%s), %s",
                    entity_id,
                    invert,
                    f"starting latency timer ({coordinator.latency_seconds}s)"
                    if coordinator.latency_seconds > 0
                    else "stopping immediately",
                )
                await _stop_with_latency()

    # Track the binary sensor
    unsub = async_track_state_change_event(
        hass, [binary_sensor_entity], _async_entity_changed
    )
    # Clean up the event subscription and any pending latency timer on unload
    entry.async_on_unload(unsub)
    entry.async_on_unload(_cancel_latency_timer)
