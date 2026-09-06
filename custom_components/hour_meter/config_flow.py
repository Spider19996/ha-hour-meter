"""Config flow for hour_meter integration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_ADJUST_PATHS,
    CONF_BINARY_SENSOR,
    CONF_CSV_PATH,
    CONF_INVERT,
    CONF_LATENCY,
    CONF_MERGE_TIME,
    CONF_NAME,
    CONF_STARTZEIT_PATH,
    DEFAULT_CSV_PATH,
    DEFAULT_DEVICE_DIR,
    DEFAULT_LATENCY_SECONDS,
    DEFAULT_MERGE_TIME_SECONDS,
    DEFAULT_STARTZEIT_PATH,
    DOMAIN,
    LOGGER,
)
from .path_validation import is_safe_config_path

if TYPE_CHECKING:
    from .data import HourMeterConfigEntry

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")
_UMLAUT_REPLACEMENTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def _slugify_name(name: str) -> str:
    """Convert a device name into a filename-friendly slug."""
    text = name.strip().lower()
    for source, replacement in _UMLAUT_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    text = _SLUG_INVALID_CHARS.sub("_", text).strip("_")
    return text or "device"


def _default_paths_for_name(name: str) -> tuple[str, str]:
    """Derive the default CSV and start time paths from the device name."""
    slug = _slugify_name(name)
    return (
        f"{DEFAULT_DEVICE_DIR}/{slug}-betriebsstunden.csv",
        f"{DEFAULT_DEVICE_DIR}/{slug}_startzeit.txt",
    )


def _get_used_csv_paths(hass) -> list[str]:
    """Get list of CSV paths already used by other config entries."""
    used_paths = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        csv_path = (
            entry.data.get(CONF_CSV_PATH) or entry.options.get(CONF_CSV_PATH) or ""
        )
        if csv_path:
            # Normalize path for comparison
            used_paths.append(str(Path(csv_path).resolve()))
    return used_paths


class HourMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for hour_meter."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._pending: dict[str, Any] = {}

    def _validate_paths(self, csv_path: str, startzeit_path: str) -> dict[str, str]:
        """Validate the configured file paths and return any errors."""
        errors: dict[str, str] = {}
        config_dir = str(self.hass.config.path())

        if not csv_path.strip():
            errors[CONF_CSV_PATH] = "csv_path_empty"
        elif not is_safe_config_path(config_dir, csv_path):
            errors[CONF_CSV_PATH] = "invalid_path"

        if not startzeit_path.strip():
            errors[CONF_STARTZEIT_PATH] = "startzeit_path_empty"
        elif not is_safe_config_path(config_dir, startzeit_path):
            errors[CONF_STARTZEIT_PATH] = "invalid_path"

        if not errors:
            # Check if CSV path is already used by another entry
            csv_path_resolved = str(Path(csv_path).resolve())
            used_paths = _get_used_csv_paths(self.hass)
            if csv_path_resolved in used_paths:
                errors[CONF_CSV_PATH] = "csv_path_already_used"
                LOGGER.warning(
                    "CSV path '%s' is already used by another device instance",
                    csv_path,
                )
        return errors

    def _build_entry_data(
        self,
        name: str,
        csv_path: str,
        startzeit_path: str,
        base_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the config entry data from the collected flow values."""
        return {
            CONF_NAME: name,
            CONF_CSV_PATH: csv_path,
            CONF_STARTZEIT_PATH: startzeit_path,
            CONF_BINARY_SENSOR: base_input.get(CONF_BINARY_SENSOR, ""),
            CONF_INVERT: base_input.get(CONF_INVERT, False),
            CONF_LATENCY: base_input.get(CONF_LATENCY, DEFAULT_LATENCY_SECONDS),
            CONF_MERGE_TIME: base_input.get(
                CONF_MERGE_TIME, DEFAULT_MERGE_TIME_SECONDS
            ),
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Use name as unique_id to allow multiple devices
            name = str(user_input.get(CONF_NAME, "Device")).strip()

            if not name:
                errors[CONF_NAME] = "name_empty"

            if not errors:
                # Check if name already exists
                await self.async_set_unique_id(f"{DOMAIN}_{name}")
                self._abort_if_unique_id_configured()

                if user_input.get(CONF_ADJUST_PATHS, False):
                    # User wants to adjust the paths - remember the input and
                    # show the path step with name-derived defaults
                    self._pending = dict(user_input)
                    return await self.async_step_paths()

                # Use the name-derived default paths
                csv_path, startzeit_path = _default_paths_for_name(name)
                errors.update(self._validate_paths(csv_path, startzeit_path))

                if not errors:
                    return self.async_create_entry(
                        title=name,
                        data=self._build_entry_data(
                            name, csv_path, startzeit_path, user_input
                        ),
                    )

        # Show form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default="Device"): str,
                    vol.Optional(CONF_ADJUST_PATHS, default=False): BooleanSelector(),
                    vol.Optional(CONF_BINARY_SENSOR): EntitySelector(
                        EntitySelectorConfig(
                            domain=["binary_sensor", "input_boolean", "switch"]
                        )
                    ),
                    vol.Optional(CONF_INVERT, default=False): BooleanSelector(),
                    vol.Optional(
                        CONF_LATENCY, default=DEFAULT_LATENCY_SECONDS
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=3600,
                            step=30,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(
                        CONF_MERGE_TIME, default=DEFAULT_MERGE_TIME_SECONDS
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=86400,
                            step=300,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_paths(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the optional path adjustment step."""
        errors: dict[str, str] = {}
        pending = self._pending
        name = str(pending.get(CONF_NAME, "Device")).strip()
        default_csv, default_startzeit = _default_paths_for_name(name)

        if user_input is not None:
            csv_path = str(user_input.get(CONF_CSV_PATH, default_csv))
            startzeit_path = str(user_input.get(CONF_STARTZEIT_PATH, default_startzeit))

            errors = self._validate_paths(csv_path, startzeit_path)

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data=self._build_entry_data(
                        name, csv_path, startzeit_path, pending
                    ),
                )

        return self.async_show_form(
            step_id="paths",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CSV_PATH, default=default_csv): str,
                    vol.Required(CONF_STARTZEIT_PATH, default=default_startzeit): str,
                }
            ),
            errors=errors,
            description_placeholders={"name": name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HourMeterOptionsFlowHandler:
        """Get the options flow for this handler."""
        return HourMeterOptionsFlowHandler(config_entry)


class HourMeterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for hour_meter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry_id = config_entry.entry_id
        self._merged = {**dict(config_entry.data), **dict(config_entry.options)}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            csv_path = user_input.get(CONF_CSV_PATH, DEFAULT_CSV_PATH)
            startzeit_path = user_input.get(CONF_STARTZEIT_PATH, DEFAULT_STARTZEIT_PATH)
            name = user_input.get(CONF_NAME, "").strip()
            config_dir = str(self.hass.config.path())

            # Validate the provided values
            if not name:
                errors[CONF_NAME] = "name_empty"

            if not csv_path.strip():
                errors[CONF_CSV_PATH] = "csv_path_empty"

            if not startzeit_path.strip():
                errors[CONF_STARTZEIT_PATH] = "startzeit_path_empty"

            if csv_path.strip() and not is_safe_config_path(config_dir, csv_path):
                errors[CONF_CSV_PATH] = "invalid_path"

            if startzeit_path.strip() and not is_safe_config_path(
                config_dir, startzeit_path
            ):
                errors[CONF_STARTZEIT_PATH] = "invalid_path"

            # Check if CSV path is already used by ANOTHER entry (not this one)
            if not errors:
                csv_path_resolved = str(Path(csv_path).resolve())
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry.entry_id == self._entry_id:
                        continue
                    entry_csv_path = (
                        entry.data.get(CONF_CSV_PATH)
                        or entry.options.get(CONF_CSV_PATH)
                        or ""
                    )
                    if (
                        entry_csv_path
                        and str(Path(entry_csv_path).resolve()) == csv_path_resolved
                    ):
                        errors[CONF_CSV_PATH] = "csv_path_already_used"
                        LOGGER.warning(
                            "CSV path '%s' is already used by another device instance",
                            csv_path,
                        )
                        break

            if not errors:
                return self.async_create_entry(
                    title=name,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=self._merged.get(CONF_NAME, "Device"),
                    ): str,
                    vol.Required(
                        CONF_CSV_PATH,
                        default=self._merged.get(CONF_CSV_PATH, DEFAULT_CSV_PATH),
                    ): str,
                    vol.Required(
                        CONF_STARTZEIT_PATH,
                        default=self._merged.get(
                            CONF_STARTZEIT_PATH, DEFAULT_STARTZEIT_PATH
                        ),
                    ): str,
                    vol.Optional(
                        CONF_BINARY_SENSOR,
                        default=self._merged.get(CONF_BINARY_SENSOR, ""),
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["binary_sensor", "input_boolean", "switch"]
                        )
                    ),
                    vol.Optional(
                        CONF_INVERT,
                        default=self._merged.get(CONF_INVERT, False),
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_LATENCY,
                        default=self._merged.get(CONF_LATENCY, DEFAULT_LATENCY_SECONDS),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=3600,
                            step=30,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(
                        CONF_MERGE_TIME,
                        default=self._merged.get(
                            CONF_MERGE_TIME, DEFAULT_MERGE_TIME_SECONDS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=86400,
                            step=300,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
            errors=errors,
        )


async def async_migrate_entry(
    hass: HomeAssistant,
    config_entry: HourMeterConfigEntry,
) -> bool:
    """Migrate an old config entry to the current format."""
    # Currently only version 1 exists - nothing to do here yet.
    return True
