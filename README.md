# SBM Defect Validation Dashboard

Streamlit dashboard for validating inline defect detections from SBM tunnel
camera images.

## Features

- Tunnel selector with `Tunnel 1`, `Tunnel 2`, and `All Tunnels`
- UID selector for grouped four-camera image captures
- Defect status display using annotations and JSON metadata
- Sidebar button for on-demand enhanced coil image viewing
- Operator validation flow with JSON metadata persistence
- Shift and validation statistics with tunnel/date filters
- Sidebar MQTT temperature display

## Setup

Install dependencies with uv:

```powershell
uv sync
```

Run the dashboard:

```powershell
uv run streamlit run src/app.py
```

## Runtime Configuration

Runtime settings are stored in:

```text
config/runtime.yaml
```

The file owns application titles, refresh timing, image paths, tunnel aliases,
operator shifts, validation choices, image extensions, and MQTT defaults.

Use a different runtime file when needed:

```powershell
$env:SBM_RUNTIME_CONFIG="config/runtime.yaml"
```

## Image Data

The configured image base path is:

```text
/home/voptimaise/Projects/SBM/received_images
```

Override it when needed:

```powershell
$env:SBM_IMAGE_BASE_DIR="/path/to/received_images"
```

Tunnel-specific paths can also be set:

```powershell
$env:SBM_TUNNEL_1_DIR="/path/to/tunnel_1"
$env:SBM_TUNNEL_2_DIR="/path/to/tunnel_2"
```

The app detects image folders under date-based storage such as:

```text
received_images/
  2026-06-16/
    coil_12345/
      camera_1.jpg
      camera_2.jpg
      camera_3.jpg
      camera_4.jpg
      metadata.json
```

Tunnel-specific layouts such as `Tunnel_1/2026-06-16/coil_12345` and
`2026-06-16/Tunnel_1/coil_12345` are also supported. The dashboard opens on
`Latest image` by default, and the UID selector can be used to view a specific
UID or coil number. JSON metadata can either match the image name
(`camera_1.json`) or be shared at the coil-folder level (`metadata.json`).
Missing folders, images, annotations, and JSON files are handled with dashboard
warnings instead of crashes.

## MQTT Temperature

The sidebar reads camera temperature messages over MQTT/TLS from:

```text
voptimaipi5.local:8883 | hotmetal/env/reading
```

Expected payload:

```json
{"sensor":"DS18B20","temp_c":35.875,"timestamp":18129,"status":"ok"}
```

The dashboard defaults match this command:

```powershell
mosquitto_sub -h voptimaipi5.local -p 8883 --cafile /etc/mosquitto/certs/ca.crt -t hotmetal/env/reading
```

When running somewhere other than the Pi, make sure the CA file is available at
the configured path or update it in the sidebar. You can also override MQTT
settings with environment variables:

```powershell
$env:MQTT_BROKERS="voptimaipi5.local"
$env:MQTT_PORT="8883"
$env:MQTT_TLS_ENABLED="true"
$env:MQTT_CA_FILE="/etc/mosquitto/certs/ca.crt"
```

## Project Structure

```text
SBM_dashboard_v1/
  config/
    runtime.yaml
  pyproject.toml
  README.md
  src/
    app.py
    runtime_config.py
    mqtt.py
    image_store.py
    metadata.py
    stats.py
    ui/
      sidebar.py
      main_page.py
      components.py
```
