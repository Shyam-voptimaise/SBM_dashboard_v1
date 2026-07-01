# SBM Defect Validation Dashboard

Streamlit dashboard for validating inline defect detections from SBM tunnel
camera images.

## Features

- Tunnel selector with `Tunnel 1`, `Tunnel 2`, and `All Tunnels`
- UID selector for grouped four-camera image captures
- Defect status display using annotations and JSON metadata
- Sidebar button for on-demand enhanced coil image viewing
- Sidebar live-image refresh controls powered by Streamlit fragments
- Operator validation flow with JSON metadata persistence
- Shift and validation statistics with tunnel/date filters
- Sidebar display for received Cam 1 and Cam 2 temperatures

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

The file owns application titles, refresh timing, image paths, temperature
paths/alerts, tunnel aliases, operator shifts, validation choices, and image
extensions.

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

The sidebar controls how often the live image workspace rescans for the newest
capture. The dashboard opens on `Latest image` by default; when that option is
selected, the fragment refresh keeps following the newest available path without
reloading the whole page.

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

## Received Camera Temperature

The receiver stores camera temperature payloads under:

```text
received_temperatures/
  2026-06-16/
    camera_temperature.jsonl
```

Each JSONL row is expected to contain a `readings` list. Common temperature and
camera field names such as `temp_c`, `temperature`, `camera_id`, `camera`,
`cam_no`, and `sensor` are supported.

```json
{
  "captured_at": "2026-06-16T10:30:00",
  "readings": [
    {"camera_id": 1, "temp_c": 42.5, "status": "ok"},
    {"camera_id": 2, "temp_c": 43.1, "status": "ok"}
  ]
}
```

The sidebar shows both camera temperatures. The dashboard raises an alert when
any camera temperature is above the configured threshold, which defaults to
`65 C`.

```powershell
$env:SBM_TEMPERATURE_DIR="/path/to/received_temperatures"
$env:SBM_TEMPERATURE_ALERT_THRESHOLD_C="65"
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
    image_store.py
    metadata.py
    stats.py
    temperature_store.py
    ui/
      sidebar.py
      main_page.py
      components.py
```
