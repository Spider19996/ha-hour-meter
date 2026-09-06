"""Unit tests for the config path validation helpers."""

from __future__ import annotations

from pathlib import Path

from custom_components.hour_meter.path_validation import is_safe_config_path


def test_absolute_path_inside_config(tmp_path: Path) -> None:
    base = str(tmp_path)
    assert is_safe_config_path(base, str(Path(tmp_path, "device", "historie.csv")))


def test_absolute_path_equal_to_config_dir(tmp_path: Path) -> None:
    base = Path(tmp_path)
    assert is_safe_config_path(str(base), str(base))


def test_relative_path_rejected(tmp_path: Path) -> None:
    assert not is_safe_config_path(str(tmp_path), "device/foo.csv")


def test_path_outside_config_rejected(tmp_path: Path) -> None:
    outside = str(Path(tmp_path).parent / "elsewhere" / "data.csv")
    assert not is_safe_config_path(str(tmp_path), outside)


def test_dotdot_escaping_config_rejected(tmp_path: Path) -> None:
    nested = str(Path(tmp_path, "device"))
    escape = str(Path(nested, "..", "..", "elsewhere", "data.csv"))
    assert not is_safe_config_path(str(tmp_path), escape)


def test_default_ha_config_paths_are_valid(tmp_path: Path) -> None:
    # The defaults live under /config which is the config dir on HA OS/Container
    base = "/config"
    assert is_safe_config_path(base, "/config/hour_meter/device-betriebsstunden.csv")
    assert is_safe_config_path(base, "/config/hour_meter/device_startzeit.txt")


def test_empty_and_blank_paths_rejected(tmp_path: Path) -> None:
    assert not is_safe_config_path(str(tmp_path), "")
    assert not is_safe_config_path(str(tmp_path), "   ")
