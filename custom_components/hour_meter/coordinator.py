"""DataUpdateCoordinator for hour_meter integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CSV_HEADER,
    CSV_VALUE,
    DATETIME_FORMAT,
    DOMAIN,
    ENTRY_TYPE_MANUELL,
    ENTRY_TYPE_RESTART,
    ENTRY_TYPE_START,
    ENTRY_TYPE_STOP,
    LOGGER,
)

UPDATE_INTERVAL = timedelta(seconds=30)

# Number of most recent CSV entries exposed on the sensor for dashboard display
MAX_CSV_ENTRIES = 25


class HourMeterCoordinator(DataUpdateCoordinator[float]):
    """Class to manage CSV data for device runtime."""

    def __init__(
        self,
        hass,
        csv_path: str,
        startzeit_path: str,
        latency_seconds: int = 120,
        merge_time_seconds: int = 300,
    ) -> None:
        """Initialize the coordinator."""
        self.csv_path = Path(csv_path)
        self.startzeit_path = Path(startzeit_path)
        self._lock = asyncio.Lock()
        self.latency_seconds = latency_seconds
        self.merge_time_seconds = merge_time_seconds

        # In-memory tracking state (avoids blocking filesystem calls in properties)
        self._tracking_active: bool = False
        # Fallback total used when the last value-carrying CSV entry
        # was removed by a merge
        self._fallback_total: float | None = None

        # Cache for the most recent CSV entries (raw lines for dashboard display)
        self.csv_data: list[str] = []

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    async def async_ensure_directories_and_files(self) -> None:
        """Ensure required directories and files exist (non-blocking)."""
        await asyncio.to_thread(self._ensure_directories_and_files)

    def _ensure_directories_and_files(self) -> None:
        """Ensure that required directories and files exist."""
        # Create CSV directory if it doesn't exist
        csv_dir = self.csv_path.parent
        if not csv_dir.exists():
            LOGGER.info("Creating directory: %s", csv_dir)
            csv_dir.mkdir(parents=True, exist_ok=True)

        # Create startzeit directory if it doesn't exist
        startzeit_dir = self.startzeit_path.parent
        if not startzeit_dir.exists():
            LOGGER.info("Creating directory: %s", startzeit_dir)
            startzeit_dir.mkdir(parents=True, exist_ok=True)

        # Create CSV file if it doesn't exist
        if not self.csv_path.exists():
            LOGGER.info("Creating CSV file: %s", self.csv_path)
            self.csv_path.touch()
            # Write CSV header
            with self.csv_path.open("w") as f:
                f.write(CSV_HEADER + "\n")

        # Create startzeit file if it doesn't exist (empty)
        if not self.startzeit_path.exists():
            LOGGER.info("Creating startzeit file: %s", self.startzeit_path)
            self.startzeit_path.touch()

    @property
    def is_tracking(self) -> bool:
        """Return True if tracking is currently active."""
        return self._tracking_active

    async def async_init_tracking_state(self) -> None:
        """Initialize the in-memory tracking flag from the marker file.

        Called once during setup so that ``is_tracking`` can rely on the
        in-memory flag instead of blocking filesystem calls.
        """
        try:
            size = await asyncio.to_thread(self._marker_file_size)
        except OSError as err:
            LOGGER.error("Error reading start time file: %s", err)
            size = 0
        self._tracking_active = size > 0

    def _marker_file_size(self) -> int:
        """Return the size of the start time marker file (0 when missing)."""
        if not self.startzeit_path.exists():
            return 0
        return self.startzeit_path.stat().st_size

    @staticmethod
    def _parse_local_datetime(value: str) -> datetime | None:
        """Parse a datetime string and treat naive values as local time.

        Runtime data is stored without a timezone (``%Y-%m-%d %H:%M:%S``). Home
        Assistant's ``parse_datetime`` returns an offset-naive datetime for such
        strings, which cannot be combined with tz-aware values like
        ``dt_util.now()``. Naive values are therefore interpreted as local time.
        """
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return dt_util.as_local(parsed)
        return parsed

    async def _async_update_data(self) -> float:
        """Read total hours and add the live runtime while tracking is active."""
        base_hours = await self._read_csv_and_data()

        # If tracking, add live runtime since start time
        if self.is_tracking:
            try:
                start_time_str = (
                    await asyncio.to_thread(self.startzeit_path.read_text)
                ).strip()
                if start_time_str and (
                    start_dt := self._parse_local_datetime(start_time_str)
                ):
                    runtime_hours = (dt_util.now() - start_dt).total_seconds() / 3600
                    base_hours = round(base_hours + runtime_hours, 2)
            except (ValueError, OSError) as err:
                LOGGER.error("Error calculating live runtime: %s", err)

        return base_hours

    def _read_tail_sync(self, max_bytes: int = 131072) -> str:
        """Read the tail of the CSV file synchronously (for use in a thread)."""
        if not self.csv_path.exists():
            return ""
        size = self.csv_path.stat().st_size
        if size == 0:
            return ""
        with self.csv_path.open("r", errors="replace") as file:
            if size <= max_bytes:
                return file.read()
            # Only read the last chunk and skip a potentially truncated first line
            file.seek(size - max_bytes)
            data = file.read()
            first_newline = data.find("\n")
            if first_newline != -1:
                data = data[first_newline + 1 :]
            return data

    async def _async_read_tail(self, max_bytes: int = 131072) -> str:
        """Read the tail of the CSV file in a thread."""
        try:
            return await asyncio.to_thread(self._read_tail_sync, max_bytes)
        except OSError as err:
            LOGGER.error("Error reading CSV file: %s", err)
            return ""

    async def _read_current_hours(self) -> float:
        """Read the current total hours from the last CSV entry."""
        try:
            content = await self._async_read_tail()
            lines = content.strip().splitlines()

            # Get the last non-empty line (skip header)
            for line in reversed(lines):
                line = line.strip()
                if line and not line.startswith("timestamp"):
                    parts = line.split(",")
                    if len(parts) > CSV_VALUE and parts[CSV_VALUE]:
                        try:
                            return float(parts[CSV_VALUE])
                        except ValueError:
                            continue
        except Exception as err:
            LOGGER.error("Error reading CSV file: %s", err)

        # No value-carrying entry found (e.g. after a merge removed the last
        # STOP entry) - fall back to the cached merge baseline.
        return self._fallback_total if self._fallback_total is not None else 0.0

    async def _read_csv_and_data(self) -> float:
        """Read the CSV file once, update the cached data lines and return total hours.

        Fills ``self.csv_data`` with the raw lines (the last ``MAX_CSV_ENTRIES``
        entries, excluding the header) so dashboard templates can render the
        recent history directly.
        """
        try:
            content = await self._async_read_tail()
            lines = content.strip().splitlines()

            if not lines or lines == [""]:
                self.csv_data = []
                return 0.0

            # Collect the last MAX_CSV_ENTRIES data lines (skip header/empty)
            data_lines: list[str] = []
            total_hours = 0.0
            has_value = False
            for line in lines:
                line = line.strip()
                if not line or line.startswith("timestamp"):
                    continue
                parts = line.split(",")
                # Update total hours from entries that carry a value
                if len(parts) > CSV_VALUE and parts[CSV_VALUE]:
                    try:
                        total_hours = float(parts[CSV_VALUE])
                        has_value = True
                    except ValueError:
                        continue
                data_lines.append(line)

            if not has_value and self._fallback_total is not None:
                # No value-carrying entry found (e.g. after a merge removed the
                # last STOP entry) - use the cached merge baseline.
                total_hours = self._fallback_total

            self.csv_data = data_lines[-MAX_CSV_ENTRIES:]
            return total_hours

        except Exception as err:
            LOGGER.error("Error reading CSV data: %s", err)
            self.csv_data = []
            return self._fallback_total if self._fallback_total is not None else 0.0

    async def _append_to_csv(self, line: str) -> None:
        """Append a line to the CSV file in a thread-safe manner."""
        async with self._lock:
            try:
                # Create file if it doesn't exist
                if not self.csv_path.exists():
                    await asyncio.to_thread(self.csv_path.touch)

                # Append line in thread
                def _write():
                    with self.csv_path.open("a") as f:
                        f.write(line + "\n")

                await asyncio.to_thread(_write)
            except OSError as err:
                LOGGER.error("Error writing to CSV file: %s", err)
                raise

    async def _read_last_entry(self) -> dict | None:
        """Read the last CSV entry for merge logic."""
        try:
            content = await self._async_read_tail()
            lines = content.strip().splitlines()

            for line in reversed(lines):
                line = line.strip()
                if line and not line.startswith("timestamp"):
                    parts = line.split(",")
                    if len(parts) >= 4:
                        return {
                            "timestamp": parts[0],
                            "typ": parts[1],
                            "wert": parts[2],
                            "laufzeit": parts[3],
                            "raw_line": line,
                        }
            return None
        except Exception as err:
            LOGGER.error("Error reading last CSV entry: %s", err)
            return None

    async def _remove_last_entry(self) -> None:
        """Remove the last line from CSV file."""
        async with self._lock:
            try:
                content = await asyncio.to_thread(self.csv_path.read_text)
                lines = content.strip().split("\n")
                # Remove last non-empty line
                new_lines = []
                removed = False
                for line in reversed(lines):
                    if (
                        not removed
                        and line.strip()
                        and not line.startswith("timestamp")
                    ):
                        removed = True
                        continue
                    new_lines.append(line)

                new_content = "\n".join(reversed(new_lines))
                if new_lines:
                    new_content += "\n"
                await asyncio.to_thread(self.csv_path.write_text, new_content)
            except OSError as err:
                LOGGER.error("Error removing last CSV entry: %s", err)

    async def async_start_tracking(self) -> None:
        """Start tracking device runtime with merge logic."""
        # Ignore if tracking is already active (idempotent)
        if self.is_tracking:
            LOGGER.info(
                "Tracking already active for %s, ignoring start request", self.csv_path
            )
            return

        now = dt_util.now()
        now_str = now.strftime(DATETIME_FORMAT)
        start_marker = now_str

        # Check if we should merge with the previous run
        if self.merge_time_seconds > 0:
            last_entry = await self._read_last_entry()
            if last_entry and last_entry["typ"] == ENTRY_TYPE_STOP:
                last_end = self._parse_local_datetime(last_entry["timestamp"])
                if last_end:
                    time_diff = (now - last_end).total_seconds()

                    if time_diff <= self.merge_time_seconds:
                        # Merge: continue the previous run without splitting the
                        # total. Remove the STOP entry, keep the total it carried
                        # as an in-memory baseline and continue counting from now
                        # so short interruptions do not show up as extra events
                        # or skew the runtime hours.
                        try:
                            self._fallback_total = float(last_entry["wert"] or 0.0)
                        except ValueError:
                            self._fallback_total = 0.0
                        await self._remove_last_entry()

                        start_marker = now_str
                        async with self._lock:
                            try:
                                await asyncio.to_thread(
                                    self.startzeit_path.write_text, start_marker
                                )
                            except OSError as err:
                                LOGGER.error("Error writing start time file: %s", err)
                                raise

                        self._tracking_active = True
                        LOGGER.info(
                            "Merging with previous entry (gap was %d seconds)",
                            time_diff,
                        )
                        await self.async_request_refresh()
                        return

        # Save start time to file
        async with self._lock:
            try:
                await asyncio.to_thread(self.startzeit_path.write_text, start_marker)
            except OSError as err:
                LOGGER.error("Error writing start time file: %s", err)
                raise

        # Write START entry to CSV
        csv_line = f"{now_str},{ENTRY_TYPE_START},,"
        await self._append_to_csv(csv_line)

        # Mark tracking active in memory
        self._tracking_active = True

        # Update sensor
        await self.async_request_refresh()

    async def async_stop_tracking(self) -> float:
        """Stop tracking device runtime and return new total hours."""
        # Ignore if no tracking is active (idempotent)
        if not self.is_tracking:
            LOGGER.warning(
                "No active tracking for %s, ignoring stop request", self.csv_path
            )
            return await self._read_current_hours()

        now = dt_util.now()
        now_str = now.strftime(DATETIME_FORMAT)
        start_time_str = ""

        # Read start time
        async with self._lock:
            try:
                if self.startzeit_path.exists():
                    start_time_str = (
                        await asyncio.to_thread(self.startzeit_path.read_text)
                    ).strip()
            except OSError as err:
                LOGGER.error("Error reading start time file: %s", err)

        # Calculate runtime
        runtime_hours = 0.0
        if start_time_str:
            start_dt = self._parse_local_datetime(start_time_str)
            if start_dt:
                runtime_hours = round((now - start_dt).total_seconds() / 3600, 2)
            else:
                LOGGER.error("Error parsing start time: %s", start_time_str)

        # Get current total hours
        current_hours = await self._read_current_hours()
        new_total = round(current_hours + runtime_hours, 2)

        # Write STOP entry to CSV
        csv_line = f"{now_str},{ENTRY_TYPE_STOP},{new_total},{runtime_hours}"
        await self._append_to_csv(csv_line)

        # Clear start time file (empty content means tracking has stopped)
        async with self._lock:
            try:
                if self.startzeit_path.exists():
                    await asyncio.to_thread(self.startzeit_path.write_text, "")
            except OSError as err:
                LOGGER.error("Error clearing start time file: %s", err)

        # Reset in-memory state
        self._tracking_active = False
        self._fallback_total = None

        # Update sensor
        await self.async_request_refresh()

        return new_total

    async def async_set_manual(self, value: float) -> None:
        """Set runtime hours manually.

        The given value is the new total, including any runtime of the
        currently active run. If tracking is active, the start marker is
        therefore reset to now so the live runtime is counted from the
        manual intervention onwards instead of being added on top of the
        value (which would double count it).
        """
        now = dt_util.now()
        now_str = now.strftime(DATETIME_FORMAT)

        # Write MANUELL entry to CSV
        csv_line = f"{now_str},{ENTRY_TYPE_MANUELL},{value},0"
        await self._append_to_csv(csv_line)

        # Reset the start marker while tracking so live runtime restarts
        # from the manual intervention
        if self.is_tracking:
            async with self._lock:
                try:
                    await asyncio.to_thread(self.startzeit_path.write_text, now_str)
                except OSError as err:
                    LOGGER.error("Error writing start time file: %s", err)

        # Update sensor
        await self.async_request_refresh()

    async def async_handle_ha_restart(
        self,
        binary_sensor_entity: str = "",
        invert: bool = False,
    ) -> None:
        """Handle HA restart - check if device was running and handle accordingly."""
        # Check if there is an active start time (device was running during restart)
        if not self._tracking_active:
            return

        # Read the start time
        start_time_str = ""
        try:
            start_time_str = (
                await asyncio.to_thread(self.startzeit_path.read_text)
            ).strip()
        except OSError as err:
            LOGGER.error("Error reading start time file: %s", err)
        if not start_time_str:
            # Marker file is empty although the in-memory flag was set - sync state
            self._tracking_active = False
            return

        LOGGER.info("Found active start time during HA restart: %s", start_time_str)

        # Determine whether the device is still running. None = unknown.
        device_still_running: bool | None = None
        if binary_sensor_entity and self.hass:
            state = self.hass.states.get(binary_sensor_entity)
            if state is None:
                LOGGER.warning("Could not read state of %s", binary_sensor_entity)
            elif state.state in ("unavailable", "unknown"):
                LOGGER.warning(
                    "Entity %s is %s during HA restart, keeping tracking active",
                    binary_sensor_entity,
                    state.state,
                )
            else:
                is_on = state.state == "on"
                if invert:
                    is_on = not is_on
                device_still_running = is_on

        if device_still_running is False:
            await self._stop_tracking_for_restart(start_time_str)
            return

        # Device is still running (or state unknown): log the restart gap and
        # continue tracking from the existing start marker.
        now_str = dt_util.now().strftime(DATETIME_FORMAT)
        csv_line = f"{now_str},{ENTRY_TYPE_RESTART},,"
        await self._append_to_csv(csv_line)
        await self.async_request_refresh()

        if device_still_running is None:
            LOGGER.warning(
                "Device was running during HA restart but the tracking entity "
                "state is unknown. Tracking continues - manual intervention may "
                "be needed."
            )
        else:
            LOGGER.info("Device is still running, continuing tracking")

    async def _stop_tracking_for_restart(self, start_time_str: str) -> None:
        """Stop tracking after a HA restart detected that the device is stopped."""
        LOGGER.info("Device stopped during HA restart, calculating runtime")
        now = dt_util.now()
        start_dt = self._parse_local_datetime(start_time_str)
        if not start_dt:
            LOGGER.error("Error parsing start time: %s", start_time_str)
            return

        runtime_hours = round((now - start_dt).total_seconds() / 3600, 2)

        # Get current total hours
        current_hours = await self._read_current_hours()
        new_total = round(current_hours + runtime_hours, 2)

        # Write STOP entry
        now_str = now.strftime(DATETIME_FORMAT)
        csv_line = f"{now_str},{ENTRY_TYPE_STOP},{new_total},{runtime_hours}"
        await self._append_to_csv(csv_line)

        # Clear start time file (empty content means tracking has stopped)
        async with self._lock:
            try:
                await asyncio.to_thread(self.startzeit_path.write_text, "")
            except OSError as err:
                LOGGER.error("Error clearing start time file: %s", err)

        # Sync in-memory state
        self._tracking_active = False
        self._fallback_total = None

        # Update sensor
        await self.async_request_refresh()

        LOGGER.info(
            "Added STOP entry for runtime before HA restart: %s hours",
            runtime_hours,
        )
