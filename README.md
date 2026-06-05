# SBM Defect Validation Dashboard

Streamlit dashboard for validating inline defect detections from SBM tunnel
camera images.

## Features

- Tunnel selector with `Tunnel 1`, `Tunnel 2`, and `All Tunnels`
- UID selector for grouped four-camera image captures
- Defect status display using annotations and JSON metadata
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
uv run streamlit run app.py
```

## Image Data

The default image base path is:

```text
/home/voptimaise/basler_sensor_photos
```

Override it when needed:

```powershell
$env:SBM_IMAGE_BASE_DIR="/path/to/basler_sensor_photos"
```

Tunnel-specific paths can also be set:

```powershell
$env:SBM_TUNNEL_1_DIR="/path/to/tunnel_1"
$env:SBM_TUNNEL_2_DIR="/path/to/tunnel_2"
```

The app detects `coil_*` folders, groups camera images by UID when possible,
and falls back to the latest four images when a UID cannot be parsed safely.
Missing folders, images, annotations, and JSON files are handled with dashboard
warnings instead of crashes.

## MQTT Temperature

The sidebar reads DS18B20 temperature messages from:

```text
hotmetal/env/reading
```

Expected payload:

```json
{"sensor":"DS18B20","temp_c":35.875,"timestamp":18129,"status":"ok"}
```

When the dashboard runs on a laptop, `localhost` is the laptop, not the Pi.
Set the MQTT broker to the Pi hostname or IP in the sidebar, or start Streamlit
with an environment variable:

```powershell
$env:MQTT_BROKERS="voptimaipi5.local,voptimaipi5,192.168.1.50"
uv run streamlit run app.py
```

## Project Structure

```text
SBM_dashboard_v1/
  app.py
  pyproject.toml
  README.md
  src/
    sbm_dashboard/
      config.py
      mqtt.py
      image_store.py
      metadata.py
      stats.py
      ui/
        sidebar.py
        main_page.py
        components.py
```
