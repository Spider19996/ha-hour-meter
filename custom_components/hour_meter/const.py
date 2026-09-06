"""Constants for hour_meter integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "hour_meter"

# Author/manufacturer shown on the device registry entries
MANUFACTURER = "Spider19996"

# Directory below the HA config dir where device files live by default
DEFAULT_DEVICE_DIR = "/config/hour_meter"

# Fallback configuration values (used when no name-derived path is available)
DEFAULT_CSV_PATH = f"{DEFAULT_DEVICE_DIR}/device-betriebsstunden.csv"
DEFAULT_STARTZEIT_PATH = f"{DEFAULT_DEVICE_DIR}/device_startzeit.txt"

# Configuration keys
CONF_NAME = "name"
CONF_CSV_PATH = "csv_path"
CONF_STARTZEIT_PATH = "startzeit_path"
CONF_ADJUST_PATHS = "adjust_paths"
CONF_BINARY_SENSOR = "binary_sensor_entity"
CONF_INVERT = "invert"
CONF_LATENCY = "latency_seconds"
CONF_MERGE_TIME = "merge_time_seconds"

# Default values
DEFAULT_LATENCY_SECONDS = 10  # 10 seconds
DEFAULT_MERGE_TIME_SECONDS = 300  # 5 minutes

# CSV file format
CSV_HEADER = "timestamp,typ,wert,laufzeit"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# CSV column indices
CSV_VALUE = 2  # index of the "wert" column (0-based)

# Entry types
ENTRY_TYPE_START = "START"
ENTRY_TYPE_STOP = "STOP"
ENTRY_TYPE_MANUELL = "MANUELL"
ENTRY_TYPE_RESTART = "HA_RESTART_LUECKE_NEUSTART"
