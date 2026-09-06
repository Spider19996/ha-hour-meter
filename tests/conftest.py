"""Shared test fixtures and a lightweight fake of the Home Assistant APIs.

The integration is designed to run inside Home Assistant. For the unit
tests we provide minimal stand-ins for the handful of ``homeassistant.*``
modules the coordinator uses so the tests run without a full HA install.
"""

from __future__ import annotations

import enum
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class Platform(str, enum.Enum):
    """Fake HA platform identifiers."""

    SENSOR = "sensor"
    NUMBER = "number"
    BINARY_SENSOR = "binary_sensor"


class ConfigEntryState(str, enum.Enum):
    """Fake config entry states."""

    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    SETUP_ERROR = "setup_error"


class Event:
    """Fake HA event placeholder."""

    def __init__(self, data: dict) -> None:
        self.data = data


class HomeAssistant:
    """Fake HA core placeholder."""

    def __init__(self, **_: object) -> None:
        pass


class ServiceCall:
    """Fake HA service call placeholder."""

    def __init__(self, domain: str, service: str, data: dict | None = None) -> None:
        self.data = data or {}


def async_track_state_change_event(*args, **kwargs):
    """Fake event tracker returning a no-op unsubscribe."""

    def _unsubscribe() -> None:
        return None

    return _unsubscribe


class FakeState:
    """Lightweight state holder for tests."""

    def __init__(self, state: str) -> None:
        self.state = state


class FakeStates:
    """Simple entity state registry."""

    def __init__(self, states: dict[str, str] | None = None) -> None:
        self._states = {k: FakeState(v) for k, v in (states or {}).items()}

    def get(self, entity_id: str) -> FakeState | None:
        return self._states.get(entity_id)


class FakeHassConfig:
    """Mirrors the small ``hass.config.path`` API used by the config flow."""

    def __init__(self, config_dir: str) -> None:
        self._config_dir = Path(config_dir)

    def path(self, *parts: str) -> str:
        return str(Path(self._config_dir, *parts))


class FakeHass:
    """Minimal Home Assistant stand-in."""

    def __init__(
        self,
        states: dict[str, str] | None = None,
        *,
        config_dir: str | None = None,
    ) -> None:
        self.states = FakeStates(states or {})
        self.config = FakeHassConfig(config_dir or str(Path("/tmp/ha-config")))


class FakeDtUtil:
    """Stand-in for ``homeassistant.util.dt``."""

    _now: datetime = datetime(2026, 9, 6, 10, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls) -> datetime:
        return cls._now

    @classmethod
    def set_now(cls, value: datetime) -> None:
        cls._now = value

    @staticmethod
    def as_local(value: datetime) -> datetime:
        """Attach the UTC tzinfo to naive datetimes (test simplification)."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def parse_datetime(value: str) -> datetime | None:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None


class FakeDataUpdateCoordinator:
    """Minimal stand-in for Home Assistant's DataUpdateCoordinator."""

    def __class_getitem__(cls, item):
        """Support ``DataUpdateCoordinator[TypeVar]`` syntax like the real class."""
        return cls

    def __init__(
        self,
        hass: FakeHass,
        logger,
        *,
        name: str | None = None,
        update_interval=None,
    ) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None

    async def async_config_entry_first_refresh(self) -> None:
        self.data = await self._async_update_data()

    async def async_request_refresh(self) -> None:
        if self.data is not None:
            # Re-run the update like DataUpdateCoordinator would
            self.data = await self._async_update_data()


def _install_fake_homeassistant() -> None:
    """Register the fake ``homeassistant`` modules in ``sys.modules``."""
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []  # make it a (namespace) package
    sys.modules["homeassistant"] = homeassistant

    ha_const = types.ModuleType("homeassistant.const")
    ha_const.Platform = Platform
    sys.modules["homeassistant.const"] = ha_const

    ha_core = types.ModuleType("homeassistant.core")
    ha_core.Event = Event
    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = ServiceCall
    sys.modules["homeassistant.core"] = ha_core

    ha_config_entries = types.ModuleType("homeassistant.config_entries")
    ha_config_entries.ConfigEntryState = ConfigEntryState
    sys.modules["homeassistant.config_entries"] = ha_config_entries

    ha_util = types.ModuleType("homeassistant.util")
    ha_util.dt = FakeDtUtil
    sys.modules["homeassistant.util"] = ha_util

    ha_helpers = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = ha_helpers

    ha_helpers_event = types.ModuleType("homeassistant.helpers.event")
    ha_helpers_event.async_track_state_change_event = async_track_state_change_event
    sys.modules["homeassistant.helpers.event"] = ha_helpers_event

    ha_helpers_upd = types.ModuleType("homeassistant.helpers.update_coordinator")
    ha_helpers_upd.DataUpdateCoordinator = FakeDataUpdateCoordinator
    sys.modules["homeassistant.helpers.update_coordinator"] = ha_helpers_upd


_install_fake_homeassistant()

# Make ``custom_components`` importable without an ``__init__.py``
sys.path.insert(0, str(REPO_ROOT))
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(REPO_ROOT / "custom_components")]
sys.modules["custom_components"] = custom_components
