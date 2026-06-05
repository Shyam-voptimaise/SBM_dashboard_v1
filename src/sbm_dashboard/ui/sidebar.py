from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from sbm_dashboard.config import (
    MQTT_BROKERS,
    MQTT_CONNECT_TIMEOUT,
    MQTT_PORT,
    MQTT_TOPIC,
    REFRESH_INTERVAL,
)
from sbm_dashboard.mqtt import extract_mqtt_command_values, start_mqtt


@dataclass(frozen=True)
class SidebarState:
    operator_name: str
    operator_id: str
    shift: str


def render_sidebar() -> SidebarState:
    st.sidebar.title("Operator Details")
    op_name = st.sidebar.text_input("Operator Name")
    op_id = st.sidebar.text_input("Operator ID")
    shift = st.sidebar.selectbox("Shift", ["A", "B", "C"])

    st.sidebar.divider()
    st.sidebar.write(f"Auto refresh every {REFRESH_INTERVAL} sec")

    # MQTT broker can be the Pi hostname/IP when running this dashboard on a laptop.
    st.sidebar.divider()
    mqtt_brokers = st.sidebar.text_input(
        "MQTT broker(s)",
        value=MQTT_BROKERS,
        help="Enter only a host/IP like localhost. Pasting mosquitto_sub -h ... also works.",
    )
    mqtt_topic = st.sidebar.text_input("MQTT topic", value=MQTT_TOPIC)
    connect_brokers, connect_topic, command_was_pasted = extract_mqtt_command_values(
        mqtt_brokers,
        mqtt_topic,
    )

    if command_was_pasted:
        st.sidebar.caption(
            f"Using broker `{connect_brokers}` and topic `{connect_topic}` from pasted command."
        )

    if st.sidebar.button("Reconnect MQTT"):
        start_mqtt.clear()
        st.rerun()

    temp_state, _mqtt_client = start_mqtt(
        connect_brokers,
        connect_topic,
        MQTT_PORT,
        MQTT_CONNECT_TIMEOUT,
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
            st.caption(f"MQTT: {broker} | {connect_topic}")
        if error:
            st.error(error)

    return SidebarState(operator_name=op_name, operator_id=op_id, shift=shift)
