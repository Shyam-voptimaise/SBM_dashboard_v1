# SBM Defect Validation Dashboard

This project is a Streamlit-based dashboard for validating defects detected in steel coils in a Special Bar Mill (SBM) setup.

## Features
- Displays latest images from multiple tunnels
- Shows annotated defect images
- Operator validation system (Defect Confirmed / False Alarm)
- Stores metadata as JSON
- Shift-wise statistics dashboard

## Setup Instructions

1. Clone or download this repository
2. Install dependencies:
   pip install -r requirements.txt

3. Run the app:
   streamlit run app.py

## MQTT Temperature
The sidebar reads DS18B20 temperature messages from:

```
hotmetal/env/reading
```

Expected payload:

```
{"sensor":"DS18B20","temp_c":35.875,"timestamp":18129,"status":"ok"}
```

When the dashboard runs on the laptop, `localhost` is the laptop, not the Pi.
Set the MQTT broker to the Pi hostname or IP in the sidebar, or start Streamlit
with an environment variable:

```
$env:MQTT_BROKERS="voptimaipi5.local,voptimaipi5,192.168.1.50"
streamlit run app.py
```

## Folder Structure
- app.py : Main Streamlit application
- requirements.txt : Python dependencies
- README.md : Project documentation

## Notes
- Update image_dir and annot_dir paths in app.py based on your system.
