# Hour Meter (Betriebsstundenzähler) - Home Assistant Custom Integration

A Home Assistant custom integration for tracking device operating hours with CSV logging.

## Features

- **UI-based setup** - Easy configuration through the Home Assistant interface
- **Multiple devices** - Add the integration multiple times to track several devices independently (each with its own device, entities, and CSV log)
- **Automatic runtime tracking** - Start/Stop services for tracking device operation
- **CSV logging** - All events are logged to a CSV file with timestamps
- **Manual override** - Set runtime hours manually if needed
- **HA restart handling** - Detects if device was running during HA restart
- **Persistent data** - Runtime data survives HA restarts
- **High value support** - Supports runtime values up to 9,999,999.9 hours
- **German translation** - Deutsche Übersetzung enthalten
- **Built-in Number entity** - Own number entity for setting runtime hours
- **Entity tracking with invert option** - Automatically start/stop tracking based on any entity (binary_sensor, input_boolean, switch) with optional inverted logic
- **Short break merging** - Consecutive runs separated by a gap shorter than the merge time are counted as one continuous run
- **Path validation** - Configured file paths are validated to stay inside the Home Assistant config directory

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Hour Meter" and install
3. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/hour_meter/` folder to your `custom_components/` directory
2. Restart Home Assistant

## Configuration

### Via UI

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Hour Meter"
3. Configure the options (see below)

To add a second (or third, ...) device, add the integration again with a **different device name**. The file paths are derived from the name automatically - or enable **Adjust paths** to choose different ones.

### Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `name` | Yes | `Device` | Unique name of the device. The default file paths are derived from it |
| `adjust_paths` | No | `false` | If enabled, an additional step appears to adjust the file paths manually |
| `csv_path` | No | `/config/device/<name>-betriebsstunden.csv` | Path to the CSV log file (derived from the device name) |
| `startzeit_path` | No | `/config/device/<name>_startzeit.txt` | Path to the start time file (derived from the device name) |
| `binary_sensor_entity` | No | - | Entity that monitors device status (binary_sensor, input_boolean, or switch) |
| `invert` | No | `false` | Enable inverted logic (entity = off means device is running) |
| `latency_seconds` | No | `10` | Delay before tracking stops after the device turns off. Prevents stopping on brief interruptions |
| `merge_time_seconds` | No | `300` | Runs separated by a gap shorter than this value are merged into one continuous run |

> **Note:** By default the file paths are derived from the device name (lowercase, umlauts converted, spaces/special characters become underscores; e.g. `Notstrom Diesel` → `/config/device/notstrom_diesel-betriebsstunden.csv`). Enable **Adjust paths** in the setup dialog to change them. Both file paths must be absolute and located inside the Home Assistant config directory (e.g. `/config/...`).

## Services

### `hour_meter.start`

Starts tracking device runtime. Saves the current timestamp to the start time file and writes a START entry to the CSV.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device` | string | No | Device name or config entry id. Only needed when multiple devices are configured. |

### `hour_meter.stop`

Stops tracking device runtime. Calculates the elapsed time, adds it to the total hours, writes a STOP entry to the CSV, and clears the start time file (the file itself is kept, empty content means the device is stopped).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device` | string | No | Device name or config entry id. Only needed when multiple devices are configured. |

### `hour_meter.manual`

Sets the runtime hours manually.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `value` | float | Yes | New total runtime hours value (e.g., 2027289.6) |
| `device` | string | No | Device name or config entry id. Only needed when multiple devices are configured. |

The value is the **new total, including the currently active run**. If tracking
is active when the value is set, the live runtime counting restarts from that
moment, so the runtime since the last start is not added on top of the value.

## Short Break Merging

When a device is stopped and restarted within the **merge time** (`merge_time_seconds`, default 5 minutes), the two runs are merged into one continuous run:

1. The previous `STOP` entry is removed from the CSV.
2. The total hours of that `STOP` entry are kept as an in-memory baseline.
3. Counting resumes from the new start; the sensor shows `baseline + live runtime`.

This makes sure short interruptions (e.g. a refuel stop) do not create extra history entries and the total never drifts. The pause itself is **not** counted as runtime.

## Sensor, Number & Binary Sensor Entities

Each device (config entry) provides its own device and three entities. The entity IDs are derived from the device name, e.g. for a device named `Garten`:

| Entity | Type | Unit | Description |
|--------|------|------|-------------|
| `sensor.garten_betriebsstunden` | Float | h | Current total device runtime hours (read-only) |
| `number.garten_betriebsstunden_eingabe` | Float | h | Input for setting runtime hours manually |
| `binary_sensor.garten_tracking_status` | Binary | - | Shows whether tracking is currently active |

With the default device name `Device` the entities are `sensor.device_betriebsstunden`, `number.device_betriebsstunden_eingabe` and `binary_sensor.device_tracking_status`.

### Using the Number Entity

The number entity allows you to set the runtime hours manually:

1. Add it to your Lovelace dashboard as a slider or input
2. When you change the value, the runtime hours are automatically updated in the CSV

```yaml
# Example Lovelace card (device named "Device")
type: entities
entities:
  - entity: sensor.device_betriebsstunden
    name: Current Runtime
  - entity: number.device_betriebsstunden_eingabe
    name: Set Runtime Hours
  - entity: binary_sensor.device_tracking_status
    name: Tracking Status
```

## CSV File Format

Each line in the CSV file has the following format:

```
timestamp,typ,wert,laufzeit
```

### Entry Types

| Type | Format | Description |
|------|--------|-------------|
| START | `2026-09-05 20:15:00,START,,` | Device started |
| STOP | `2026-09-05 22:45:00,STOP,2027289.6,2.5` | Device stopped with total hours and runtime |
| MANUELL | `2026-09-05 18:00:00,MANUELL,2027289.6,0` | Manual value entry |
| HA_RESTART | `2026-09-05 08:00:00,HA_RESTART_LUECKE_NEUSTART,,` | HA restart detected with active tracking |

## CSV-Verlauf im Dashboard anzeigen

Der Sensor `sensor.device_betriebsstunden` stellt die letzten 25 CSV-Einträge als Attribut `csv_data` bereit (aktualisiert sich alle 30 Sekunden). Damit kannst du den Verlauf als Tabelle direkt in einer Markdown-Card anzeigen:

```yaml
type: markdown
title: Betriebsstunden Verlauf
content: >-
  <table style="width:100%; border-collapse: collapse;">
  <tr><th>Zeitstempel</th><th>Ereignis</th><th>Stunden gesamt</th><th>Laufzeit (h)</th></tr>
  {%- for line in state_attr('sensor.device_betriebsstunden', 'csv_data') | default([]) %}
  {%- set cols = line.split(',') %}
  {%- if cols | length >= 4 %}
  <tr><td>{{ cols[0] if cols[0] else '—' }}</td><td>{{ cols[1] }}</td><td>{{ cols[2] if cols[2] else '—' }}</td><td>{{ cols[3] if cols[3] else '—' }}</td></tr>
  {%- endif %}
  {%- endfor %}
  </table>
```

**Hinweise:**
- Es werden höchstens die **letzten 25 Einträge** angezeigt.
- Das Attribut wird alle **30 Sekunden** aktualisiert.
- Bei mehreren Geräten einfach die passende Sensor-Entity verwenden, z.B. `sensor.garten_betriebsstunden`.

## Automatic Entity Tracking

The integration can automatically track runtime based on any entity (binary_sensor, input_boolean, or switch).

### Configuration

In the integration configuration:
1. Select an entity that monitors the device status
2. Optionally enable **Invert** if the logic is inverted

### How It Works

| Entity State | Invert = false | Invert = true |
|--------------|----------------|---------------|
| `on` | Tracking starts | Tracking stops |
| `off` | Tracking stops | Tracking starts |

### Example

Configure `binary_sensor.device_laeuft` as the tracking entity:
- Device starts → binary_sensor = `on` → tracking starts automatically
- Device stops → binary_sensor = `off` → tracking stops and runtime is saved

### Inverted Logic Example

Some sensors report `0` when the device is running and `1` when stopped:
- Enable **Invert** option
- Sensor = `0` (off) → tracking starts
- Sensor = `1` (on) → tracking stops

## Manual Service Calls

You can also use the services directly in automations or scripts:

### Start tracking:
```yaml
action: hour_meter.start
```

Start tracking a specific device (when multiple are configured):
```yaml
action: hour_meter.start
data:
  device: "Garten"
```

### Stop tracking:
```yaml
action: hour_meter.stop
```

### Set manual value:
```yaml
action: hour_meter.manual
data:
  value: 2027289.6
```

## Troubleshooting

### Check logs
Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.hour_meter: debug
```

### Verify file permissions
Ensure the Home Assistant user has write access to the CSV and start time file locations.

## Development

To run the linter and tests locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check custom_components tests
ruff format --check custom_components tests
pytest
```

The CI pipeline (`.github/workflows/ci.yml`) runs `ruff`, the unit tests, the Home Assistant `hassfest` checks and the HACS validation on every push and pull request.

## License

MIT License
