from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from mqtt import (
    MqttConnectionSettings,
    TemperatureState,
    extract_mqtt_command_values,
    start_mqtt,
)
from runtime_config import (
    MQTT_BROKERS,
    MQTT_CA_FILE,
    MQTT_CONNECT_TIMEOUT,
    MQTT_PORT,
    MQTT_TLS_ENABLED,
    MQTT_TOPIC,
    SHIFTS,
)


@dataclass(frozen=True)
class SidebarState:
    operator_name: str
    operator_id: str
    shift: str


def _short_payload(payload: Any) -> str:
    text = str(payload)
    return text if len(text) <= 160 else f"{text[:157]}..."


def _ca_file_missing(mqtt_settings: MqttConnectionSettings) -> bool:
    ca_file = mqtt_settings.ca_file.strip()
    return (
        mqtt_settings.tls_enabled
        and bool(ca_file)
        and not Path(ca_file).expanduser().exists()
    )


@st.fragment(run_every="1s")
def render_temperature_panel(
    temp_state: TemperatureState,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    latest_temp = temp_state.snapshot()
    val = latest_temp.get("value")
    ts = latest_temp.get("updated_at")
    sensor = latest_temp.get("sensor")
    sensor_status = latest_temp.get("sensor_status")
    broker = latest_temp.get("broker")
    connected = latest_temp.get("connected")
    error = latest_temp.get("error")
    raw_payload = latest_temp.get("raw_payload")

    st.markdown("### Temperature")

    if val is None:
        if connected:
            st.info("Connected, waiting for temperature message")
        else:
            st.warning("MQTT not connected")
    else:
        st.metric(label="Temperature", value=f"{val:.2f} C")
        if ts:
            st.caption(f"Updated: {ts}")

    if sensor:
        st.caption(f"Sensor: {sensor}")
    if sensor_status:
        st.caption(f"Sensor status: {sensor_status}")

    security = "TLS" if mqtt_settings.tls_enabled else "Plain"
    broker_label = broker or f"{mqtt_settings.brokers}:{mqtt_settings.port}"
    st.caption(f"MQTT: {broker_label} | {mqtt_settings.topic} | {security}")

    if _ca_file_missing(mqtt_settings):
        st.warning(f"CA file not found: {mqtt_settings.ca_file}")
    if raw_payload and val is None:
        st.caption(f"Last payload: {_short_payload(raw_payload)}")
    if error:
        st.error(error)


def render_sidebar() -> SidebarState:
    st.sidebar.title("Operator Details")
    op_name = st.sidebar.text_input("Operator Name")
    op_id = st.sidebar.text_input("Operator ID")
    shift = st.sidebar.selectbox("Shift", SHIFTS)

    st.sidebar.divider()
    st.sidebar.write("Dashboard auto-refresh off")

    # MQTT broker can be the Pi hostname/IP when running this dashboard on a laptop.
    st.sidebar.divider()
    mqtt_brokers = st.sidebar.text_input(
        "MQTT broker(s)",
        value=MQTT_BROKERS,
        help="Enter only a host/IP like localhost. Pasting mosquitto_sub -h ... also works.",
    )
    mqtt_port = st.sidebar.number_input(
        "MQTT port",
        min_value=1,
        max_value=65535,
        value=MQTT_PORT,
        step=1,
    )
    mqtt_topic = st.sidebar.text_input("MQTT topic", value=MQTT_TOPIC)
    mqtt_tls_enabled = st.sidebar.checkbox("MQTT TLS", value=MQTT_TLS_ENABLED)
    mqtt_ca_file = st.sidebar.text_input("MQTT CA file", value=MQTT_CA_FILE)

    mqtt_settings = extract_mqtt_command_values(
        mqtt_brokers,
        mqtt_topic,
        int(mqtt_port),
        mqtt_tls_enabled,
        mqtt_ca_file,
    )

    if mqtt_settings.command_was_pasted:
        tls_text = "TLS enabled" if mqtt_settings.tls_enabled else "TLS disabled"
        st.sidebar.caption(
            f"Using `{mqtt_settings.brokers}:{mqtt_settings.port}` and topic `{mqtt_settings.topic}` from pasted command. {tls_text}."
        )

    if st.sidebar.button("Reconnect MQTT"):
        start_mqtt.clear()
        st.rerun()

    temp_state, _mqtt_client = start_mqtt(
        mqtt_settings.brokers,
        mqtt_settings.topic,
        mqtt_settings.port,
        MQTT_CONNECT_TIMEOUT,
        mqtt_settings.tls_enabled,
        mqtt_settings.ca_file,
    )

    with st.sidebar:
        render_temperature_panel(temp_state, mqtt_settings)

    return SidebarState(operator_name=op_name, operator_id=op_id, shift=shift)
