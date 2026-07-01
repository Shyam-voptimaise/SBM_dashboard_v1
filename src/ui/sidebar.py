from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st

from runtime_config import (
    REFRESH_INTERVAL,
    SHIFTS,
    TEMPERATURE_ALERT_THRESHOLD_C,
    TEMPERATURE_BASE_DIR,
    TEMPERATURE_REFRESH_SECONDS,
)
from temperature_store import (
    CameraTemperature,
    latest_temperature_snapshot,
    over_temperature_readings,
)


@dataclass(frozen=True)
class SidebarState:
    operator_name: str
    operator_id: str
    shift: str
    enhance_images: bool
    auto_refresh_images: bool
    image_refresh_seconds: int


def _temperature_by_camera(
    readings: tuple[CameraTemperature, ...],
) -> dict[int, CameraTemperature]:
    return {reading.camera_number: reading for reading in readings}


def _format_temperature(value_c: float | None) -> str:
    return f"{value_c:.1f} C" if value_c is not None else "--"


def _temperature_style(value_c: float | None) -> str:
    if value_c is not None and value_c > TEMPERATURE_ALERT_THRESHOLD_C:
        return "color:#b91c1c;font-weight:700;"
    return "color:#111827;font-weight:700;"


def _temperature_card(
    label: str,
    value_c: float | None,
) -> str:
    return (
        '<div style="flex:1 1 5.8rem;min-width:5.8rem;'
        'border:1px solid #e5e7eb;border-radius:6px;'
        'padding:0.42rem 0.5rem;background:#ffffff;">'
        '<div style="font-size:0.68rem;font-weight:700;color:#6b7280;'
        f'letter-spacing:0;">{html.escape(label)}</div>'
        f'<div style="font-size:0.95rem;line-height:1.2;{_temperature_style(value_c)}">'
        f"{html.escape(_format_temperature(value_c))}</div>"
        "</div>"
    )


def _format_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _render_temperature_contents() -> None:
    snapshot = latest_temperature_snapshot(TEMPERATURE_BASE_DIR)
    readings_by_camera = _temperature_by_camera(snapshot.readings)
    hot_readings = over_temperature_readings(
        snapshot.readings,
        TEMPERATURE_ALERT_THRESHOLD_C,
    )

    cam_1 = readings_by_camera.get(1)
    cam_2 = readings_by_camera.get(2)
    cam_1_value = cam_1.value_c if cam_1 else None
    cam_2_value = cam_2.value_c if cam_2 else None

    temperature_html = (
        '<div style="margin:0.35rem 0 0.6rem 0;">'
        '<div style="font-size:0.88rem;font-weight:700;color:#111827;'
        'line-height:1.15;margin-bottom:0.35rem;">Camera Temperature</div>'
        '<div style="display:flex;gap:0.45rem;align-items:stretch;">'
        f'{_temperature_card("CAM 1", cam_1_value)}'
        f'{_temperature_card("CAM 2", cam_2_value)}'
        "</div>"
        "</div>"
    )
    st.markdown(temperature_html, unsafe_allow_html=True)

    for reading in hot_readings:
        st.error(
            f"{reading.label} temperature high: "
            f"{reading.value_c:.1f} C"
        )

    updated_at = (
        snapshot.captured_at
        or max(
            (
                reading.captured_at
                for reading in snapshot.readings
                if reading.captured_at is not None
            ),
            default=None,
        )
        or snapshot.updated_at
    )
    updated_text = _format_timestamp(updated_at)
    if updated_text:
        st.caption(f"Last received: {updated_text}")


def _render_temperature_panel() -> None:
    @st.fragment(run_every=max(1, int(TEMPERATURE_REFRESH_SECONDS)))
    def render_received_temperature() -> None:
        with st.container():
            _render_temperature_contents()

    with st.sidebar:
        render_received_temperature()


def render_sidebar() -> SidebarState:
    st.sidebar.markdown("### Operator Details")
    op_name = st.sidebar.text_input("Operator Name")
    op_id = st.sidebar.text_input("Operator ID")
    shift = st.sidebar.selectbox("Shift", SHIFTS)
    _render_temperature_panel()

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

    st.sidebar.divider()
    st.sidebar.markdown("### Live Images")
    auto_refresh_images = st.sidebar.toggle(
        "Auto refresh",
        value=True,
        key="auto_refresh_images",
    )
    default_refresh_interval = max(10, min(int(REFRESH_INTERVAL), 120))
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

    return SidebarState(
        operator_name=op_name,
        operator_id=op_id,
        shift=shift,
        enhance_images=enhance_images,
        auto_refresh_images=auto_refresh_images,
        image_refresh_seconds=image_refresh_seconds,
    )
