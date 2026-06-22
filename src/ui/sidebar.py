from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from mqtt import extract_mqtt_command_values, start_mqtt
from runtime_config import (
    MQTT_BROKERS,
    MQTT_CA_FILE,
    MQTT_CONNECT_TIMEOUT,
    MQTT_PORT,
    MQTT_TLS_ENABLED,
    MQTT_TOPIC,
    REFRESH_INTERVAL,
    SHIFTS,
)


@dataclass(frozen=True)
class SidebarState:
    operator_name: str
    operator_id: str
    shift: str
    enhance_images: bool
    auto_refresh_images: bool
    image_refresh_seconds: int


def render_sidebar() -> SidebarState:
    st.sidebar.title("Operator Details")
    op_name = st.sidebar.text_input("Operator Name")
    op_id = st.sidebar.text_input("Operator ID")
    shift = st.sidebar.selectbox("Shift", SHIFTS)

    st.sidebar.divider()
    st.sidebar.markdown("### Image View")
    enhance_images = bool(st.session_state.get("enhance_coil_images", False))
    enhance_label = (
        "Show Original Coil Photo" if enhance_images else "Enhance Coil Photo"
    )
    if st.sidebar.button(enhance_label, use_container_width=True):
        st.session_state["enhance_coil_images"] = not enhance_images
        st.rerun()
    enhance_images = bool(st.session_state.get("enhance_coil_images", False))
    st.sidebar.caption(
        f"Current view: {'Enhanced' if enhance_images else 'Original'}"
    )

    st.sidebar.divider()
    st.sidebar.markdown("### Live Images")
    auto_refresh_images = st.sidebar.toggle(
        "Auto refresh",
        value=True,
        key="auto_refresh_images",
    )
    default_refresh_interval = max(1, min(int(REFRESH_INTERVAL), 120))
    image_refresh_seconds = int(
        st.sidebar.slider(
            "Refresh interval",
            min_value=1,
            max_value=120,
            value=default_refresh_interval,
            step=1,
            format="%d sec",
            disabled=not auto_refresh_images,
            key="image_refresh_seconds",
        )
    )
    if st.sidebar.button("Refresh Images Now", use_container_width=True):
        st.rerun()

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
    latest_temp = temp_state.snapshot()
    latest_temp["ts"] = latest_temp.get("updated_at")

    with st.sidebar:
        st.markdown("### Temperature")
        temp_display = st.empty()
        ts_display = st.empty()

        val = latest_temp.get("value")
        ts = latest_temp.get("ts")
        sensor_status = latest_temp.get("sensor_status")
        broker = latest_temp.get("broker")
        error = latest_temp.get("error")

        if val is None:
            temp_display.info("No temperature reading yet")
        else:
            temp_display.metric(label="Temperature", value=f"{val:.2f} C")
            if ts:
                ts_display.caption(f"Updated: {ts}")

        if sensor_status:
            st.caption(f"Sensor: {sensor_status}")
        if broker:
            security = "TLS" if mqtt_settings.tls_enabled else "Plain"
            st.caption(f"MQTT: {broker} | {mqtt_settings.topic} | {security}")
        if error:
            st.error(error)

    return SidebarState(
        operator_name=op_name,
        operator_id=op_id,
        shift=shift,
        enhance_images=enhance_images,
        auto_refresh_images=auto_refresh_images,
        image_refresh_seconds=image_refresh_seconds,
    )
