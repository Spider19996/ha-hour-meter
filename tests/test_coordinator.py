"""Unit tests for the HourMeterCoordinator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from custom_components.hour_meter.coordinator import (
    HourMeterCoordinator,
)

from conftest import FakeDtUtil, FakeHass

CSV_HEADER = "timestamp,typ,wert,laufzeit"


def _advance(minutes: int = 0, hours: int = 0) -> None:
    """Advance the fake clock."""
    FakeDtUtil.set_now(FakeDtUtil.now() + timedelta(hours=hours, minutes=minutes))


def _read_lines(path) -> list[str]:
    """Read the CSV file as non-empty lines."""
    content = path.read_text().strip()
    return [line for line in content.splitlines() if line.strip()]


def _last_line(path) -> str:
    return _read_lines(path)[-1]


@pytest.fixture
async def coordinator(tmp_path):
    """Create a fresh coordinator backed by temp files."""
    FakeDtUtil.set_now(datetime(2026, 9, 6, 10, 0, 0, tzinfo=timezone.utc))
    co = HourMeterCoordinator(
        hass=FakeHass(),
        csv_path=str(tmp_path / "historie.csv"),
        startzeit_path=str(tmp_path / "start.txt"),
        latency_seconds=10,
        merge_time_seconds=300,
    )
    await co.async_ensure_directories_and_files()
    await co.async_config_entry_first_refresh()
    await co.async_init_tracking_state()
    return co


async def test_start_stop_tracking(coordinator, tmp_path) -> None:
    """A normal start/stop cycle writes proper entries and tracks the total."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_start_tracking()
    assert coordinator.is_tracking
    lines = _read_lines(csv_path)
    assert lines[-1] == "2026-09-06 10:00:00,START,,"

    _advance(hours=2)
    await coordinator.async_request_refresh()
    # Live runtime is added on top of the stored total
    assert coordinator.data == pytest.approx(2.0)

    new_total = await coordinator.async_stop_tracking()
    assert new_total == pytest.approx(2.0)
    assert not coordinator.is_tracking

    lines = _read_lines(csv_path)
    assert lines[0] == CSV_HEADER
    stop = lines[-1].split(",")
    assert stop[1] == "STOP"
    assert float(stop[2]) == pytest.approx(2.0)
    assert float(stop[3]) == pytest.approx(2.0)


async def test_merge_preserves_total(coordinator, tmp_path) -> None:
    """Merging short runs keeps the accumulated total instead of losing it."""
    csv_path = tmp_path / "historie.csv"

    # First run: 30 minutes
    await coordinator.async_start_tracking()
    _advance(minutes=30)
    await coordinator.async_stop_tracking()
    assert not coordinator.is_tracking

    # Restart 5 minutes later (within merge_time_seconds=300) -> merge
    _advance(minutes=5)
    await coordinator.async_start_tracking()
    assert coordinator.is_tracking
    # The STOP entry of the first run must be gone and the total it carried
    # must be preserved as an in-memory baseline. Counting resumes from now,
    # so the 5 minute gap is not counted as runtime.
    marker = coordinator.startzeit_path.read_text().strip()
    assert marker == "2026-09-06 10:35:00"

    # Second leg of the merged run: another hour
    _advance(hours=1)
    await coordinator.async_request_refresh()
    # 0.5 h from the first leg + 1.0 h from the second leg
    assert coordinator.data == pytest.approx(1.5)

    new_total = await coordinator.async_stop_tracking()
    assert new_total == pytest.approx(1.5)

    lines = _read_lines(csv_path)
    # header + original START + final STOP only
    assert len(lines) == 3
    assert lines[1] == "2026-09-06 10:00:00,START,,"
    stop = lines[-1].split(",")
    assert stop[1] == "STOP"
    assert float(stop[2]) == pytest.approx(1.5)
    assert float(stop[3]) == pytest.approx(1.0)


async def test_no_merge_when_gap_too_long(coordinator, tmp_path) -> None:
    """Runs separated by more than the merge time are tracked separately."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_start_tracking()
    _advance(minutes=30)
    await coordinator.async_stop_tracking()

    # 10 minutes > merge_time_seconds=300 -> no merge
    _advance(minutes=10)
    await coordinator.async_start_tracking()
    assert coordinator.is_tracking
    assert coordinator.startzeit_path.read_text().strip() == "2026-09-06 10:40:00"

    _advance(minutes=30)
    await coordinator.async_stop_tracking()
    assert not coordinator.is_tracking

    lines = _read_lines(csv_path)
    # header + START + STOP + START + STOP
    assert len(lines) == 5
    assert [line.split(",")[1] for line in lines[1:]] == [
        "START",
        "STOP",
        "START",
        "STOP",
    ]
    assert float(_last_line(csv_path).split(",")[2]) == pytest.approx(1.0)


async def test_manual_value(coordinator, tmp_path) -> None:
    """Setting a manual value writes a MANUELL entry and updates the total."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_set_manual(2027289.6)
    assert coordinator.data == pytest.approx(2027289.6)

    lines = _read_lines(csv_path)
    manual = lines[-1].split(",")
    assert manual[1] == "MANUELL"
    assert float(manual[2]) == pytest.approx(2027289.6)


async def test_manual_value_during_tracking_resets_marker(
    coordinator, tmp_path
) -> None:
    """A manual value while tracking counts live runtime only from now on."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_start_tracking()
    _advance(hours=2)

    # The manual value replaces the total including the active run
    await coordinator.async_set_manual(100.0)
    assert coordinator.is_tracking

    # The start marker must have been reset to the current (fake) time
    assert coordinator.startzeit_path.read_text().strip() == "2026-09-06 12:00:00"

    # Live runtime continues from the manual intervention, not from 10:00
    _advance(minutes=30)
    await coordinator.async_request_refresh()
    assert coordinator.data == pytest.approx(100.5)

    new_total = await coordinator.async_stop_tracking()
    assert new_total == pytest.approx(100.5)
    assert not coordinator.is_tracking

    stop = _last_line(csv_path).split(",")
    assert stop[1] == "STOP"
    assert float(stop[2]) == pytest.approx(100.5)
    assert float(stop[3]) == pytest.approx(0.5)


async def test_restart_device_still_running(coordinator, tmp_path) -> None:
    """Restart with the device still running logs a HA_RESTART entry."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_start_tracking()
    coordinator.hass = FakeHass(states={"binary_sensor.gen": "on"})

    _advance(hours=1)
    await coordinator.async_handle_ha_restart("binary_sensor.gen")

    assert coordinator.is_tracking
    last = _last_line(csv_path).split(",")
    assert last[1] == "HA_RESTART_LUECKE_NEUSTART"


async def test_restart_device_stopped(coordinator, tmp_path) -> None:
    """Restart with the device stopped finalizes the runtime."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_start_tracking()
    coordinator.hass = FakeHass(states={"binary_sensor.gen": "off"})

    _advance(hours=2)
    await coordinator.async_handle_ha_restart("binary_sensor.gen")

    assert not coordinator.is_tracking
    last = _last_line(csv_path).split(",")
    assert last[1] == "STOP"
    assert float(last[3]) == pytest.approx(2.0)
    assert float(last[2]) == pytest.approx(2.0)


async def test_restart_unknown_state_keeps_tracking(coordinator, tmp_path) -> None:
    """Restart with an unavailable tracking entity keeps tracking running."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_start_tracking()
    coordinator.hass = FakeHass(states={"binary_sensor.gen": "unavailable"})

    await coordinator.async_handle_ha_restart("binary_sensor.gen")

    assert coordinator.is_tracking
    last = _last_line(csv_path).split(",")
    assert last[1] == "HA_RESTART_LUECKE_NEUSTART"


async def test_restart_without_tracking_does_nothing(coordinator, tmp_path) -> None:
    """Without an active marker the restart handler is a no-op."""
    csv_path = tmp_path / "historie.csv"

    await coordinator.async_handle_ha_restart("binary_sensor.gen")

    assert not coordinator.is_tracking
    assert _read_lines(csv_path) == [CSV_HEADER]
