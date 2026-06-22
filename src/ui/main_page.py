from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from image_store import ImageGroup, image_groups_for_tunnel
from metadata import load_image_metadata, save_image_metadata
from runtime_config import (
    ALL_TUNNELS,
    TUNNEL_FILTER_OPTIONS,
    TUNNEL_NAMES,
    TUNNELS,
    UNVALIDATED_DECISION,
    VALIDATION_DECISIONS,
)
from stats import (
    collect_metadata_records,
    filter_records,
    get_coil_status,
    records_to_dataframe,
    summary_counts,
)
from ui.components import (
    open_image,
    render_image_grid,
    render_status_badge,
)
from ui.sidebar import SidebarState

LATEST_GROUP_SELECTION = "__latest_image__"


def _key(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def _groups_for_tunnel(tunnel_name: str) -> list[ImageGroup]:
    return image_groups_for_tunnel(tunnel_name, TUNNELS[tunnel_name])


def _group_identity(group: ImageGroup) -> str:
    return f"{group.coil_folder}::{group.uid}"


def _group_key(group: ImageGroup) -> str:
    return _key(f"{group.coil}_{group.uid}")


def _group_by_identity(
    groups: list[ImageGroup],
    identity: str | None,
) -> ImageGroup | None:
    if not groups:
        return None
    if identity in (None, LATEST_GROUP_SELECTION):
        return groups[0]
    for group in groups:
        if _group_identity(group) == identity:
            return group
    return groups[0]


def _uid_label(group: ImageGroup, uid_counts: Counter[str]) -> str:
    if uid_counts[group.uid] <= 1:
        return group.uid
    return f"{group.uid} ({group.coil})"


def _uid_option_label(
    identity: str,
    groups_by_identity: dict[str, ImageGroup],
    uid_counts: Counter[str],
) -> str:
    if identity == LATEST_GROUP_SELECTION:
        return "Latest image"
    return _uid_label(groups_by_identity[identity], uid_counts)


def _selected_or_latest_group(
    tunnel_name: str,
    groups: list[ImageGroup],
) -> ImageGroup | None:
    selected_group = st.session_state.get(f"selected_group_{_key(tunnel_name)}")
    return _group_by_identity(groups, selected_group)


def _metadata_target_image(group: ImageGroup) -> Path | None:
    for image in group.images:
        if load_image_metadata(image):
            return image
    return group.primary_image


def render_main_page(sidebar_state: SidebarState) -> None:
    top_left, top_right = st.columns([1, 1])

    with top_left:
        tunnel_choice = st.selectbox(
            "Tunnel",
            TUNNEL_FILTER_OPTIONS,
            index=0,
            key="main_tunnel_choice",
        )

    if tunnel_choice == ALL_TUNNELS:
        with top_right:
            st.selectbox(
                "UID",
                ["UID selection is tunnel-specific"],
                disabled=True,
                key="main_uid_disabled",
            )

        for tunnel_name in TUNNEL_NAMES:
            groups = _groups_for_tunnel(tunnel_name)
            group = _selected_or_latest_group(tunnel_name, groups)
            render_tunnel_section(
                tunnel_name=tunnel_name,
                group=group,
                sidebar_state=sidebar_state,
                section_key=f"all_{_key(tunnel_name)}",
                show_heading=True,
            )
    else:
        groups = _groups_for_tunnel(tunnel_choice)
        group_options = (
            [LATEST_GROUP_SELECTION, *[_group_identity(group) for group in groups]]
            if groups
            else []
        )
        groups_by_identity = {_group_identity(group): group for group in groups}
        uid_counts = Counter(group.uid for group in groups)
        selected_group: str | None = None

        with top_right:
            if group_options:
                selected_group = st.selectbox(
                    "UID",
                    group_options,
                    format_func=lambda identity: _uid_option_label(
                        identity,
                        groups_by_identity,
                        uid_counts,
                    ),
                    key=f"uid_select_{_key(tunnel_choice)}",
                )
                st.session_state[
                    f"selected_group_{_key(tunnel_choice)}"
                ] = selected_group
            else:
                st.selectbox(
                    "UID",
                    ["No UIDs available"],
                    disabled=True,
                    key=f"uid_select_empty_{_key(tunnel_choice)}",
                )

        group = _group_by_identity(groups, selected_group)
        render_tunnel_section(
            tunnel_name=tunnel_choice,
            group=group,
            sidebar_state=sidebar_state,
            section_key=_key(tunnel_choice),
            show_heading=False,
        )

    render_stats_section()


def render_tunnel_section(
    tunnel_name: str,
    group: ImageGroup | None,
    sidebar_state: SidebarState,
    section_key: str,
    show_heading: bool,
) -> None:
    if show_heading:
        st.subheader(tunnel_name)

    if group is None:
        st.warning(f"No coil images found for {tunnel_name}.")
        return

    image_column, status_column = st.columns([3, 1])
    group_key = _group_key(group)

    with image_column:
        st.info(f"Current Coil: {group.coil}")
        with st.container(border=True):
            st.markdown(f"**UID:** `{group.uid}`")
            render_image_grid(
                group.images,
                f"{section_key}_{group_key}",
                enhance_images=sidebar_state.enhance_images,
            )

    with status_column:
        render_status_panel(group)

    render_annotations(group)
    render_defect_and_validation(group, sidebar_state, section_key)


def render_status_panel(group: ImageGroup) -> None:
    status = get_coil_status(
        group.metadata,
        tuple(str(path) for path in group.annotations),
    )
    with st.container(border=True):
        st.markdown("### Coil Status")
        render_status_badge(status)
        st.caption(f"Tunnel: {group.tunnel}")
        st.caption(f"Coil: {group.coil}")
        st.caption(f"UID: {group.uid}")


def render_annotations(group: ImageGroup) -> None:
    if not group.annotations:
        return

    st.markdown("### Defect Detected")
    columns = st.columns(min(4, len(group.annotations)))
    for index, annotation_path in enumerate(group.annotations[:4]):
        with columns[index % len(columns)]:
            image = open_image(annotation_path)
            if image is None:
                st.warning(f"Could not load {annotation_path.name}")
            else:
                st.image(
                    image,
                    caption=annotation_path.name,
                    use_container_width=True,
                )


def render_defect_and_validation(
    group: ImageGroup,
    sidebar_state: SidebarState,
    section_key: str,
) -> None:
    details_column, decision_column = st.columns([1, 1])

    with details_column:
        st.markdown("### Detected Defects")
        defects = group.metadata.get("defects")
        if isinstance(defects, list) and defects:
            for defect in defects:
                if isinstance(defect, dict):
                    defect_type = defect.get("type", "Unknown")
                    severity = defect.get("severity", "NA")
                    confidence = defect.get("confidence", "NA")
                    st.markdown(f"- **{defect_type}** | {severity} | {confidence}")
                else:
                    st.markdown(f"- {defect}")
        else:
            st.info("No defect data available")

    with decision_column:
        render_validation_form(group, sidebar_state, section_key)


def render_validation_form(
    group: ImageGroup,
    sidebar_state: SidebarState,
    section_key: str,
) -> None:
    decision = st.radio(
        f"Final Decision - {group.tunnel}",
        VALIDATION_DECISIONS,
        key=f"dec_{section_key}_{_group_key(group)}",
    )

    remark = st.text_area(
        f"Remarks - {group.tunnel}",
        key=f"rem_{section_key}_{_group_key(group)}",
    )

    if st.button(
        f"Save Decision - {group.tunnel}",
        key=f"save_{section_key}_{_group_key(group)}",
    ):
        primary_image = _metadata_target_image(group)
        if primary_image is None:
            st.error("No image is available for this UID.")
            return

        if not sidebar_state.operator_name or not sidebar_state.operator_id:
            st.error("Operator details required")
            return

        if decision == UNVALIDATED_DECISION:
            st.error("Please select a decision")
            return

        metadata = load_image_metadata(primary_image)
        metadata.setdefault("defects", [])
        metadata.update(
            {
                "operator_name": sidebar_state.operator_name,
                "operator_id": sidebar_state.operator_id,
                "shift": sidebar_state.shift,
                "operator_decision": decision,
                "tunnel": group.tunnel,
                "uid": group.uid,
                "remarks": remark,
                "validated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "coil": group.coil,
            }
        )

        try:
            save_image_metadata(primary_image, metadata)
        except OSError as exc:
            st.error(f"Could not save decision: {exc}")
            return

        st.success("Saved successfully")
        st.rerun()


def render_stats_section() -> None:
    st.divider()
    st.subheader("Validation Statistics")

    records = collect_metadata_records(TUNNELS)
    record_dates = [record["_date"] for record in records if record.get("_date")]
    today = date.today()
    min_date = min(record_dates) if record_dates else today
    max_date = max(record_dates) if record_dates else today

    filter_col, from_col, to_col = st.columns([1, 1, 1])
    with filter_col:
        tunnel_filter = st.selectbox(
            "Stats Tunnel",
            TUNNEL_FILTER_OPTIONS,
            index=len(TUNNEL_NAMES),
            key="stats_tunnel_filter",
        )
    with from_col:
        from_date = st.date_input("From date", value=min_date, key="stats_from_date")
    with to_col:
        to_date = st.date_input("To date", value=max_date, key="stats_to_date")

    if from_date > to_date:
        st.warning("From date must be earlier than or equal to To date.")
        return

    filtered_records = filter_records(records, tunnel_filter, from_date, to_date)
    counts = summary_counts(filtered_records)

    metric_columns = st.columns(len(counts))
    for column, (label, value) in zip(metric_columns, counts.items()):
        column.metric(label, value)

    dataframe = records_to_dataframe(filtered_records)
    if dataframe.empty:
        st.info("No validation records found for the selected filters.")
    else:
        st.dataframe(dataframe, use_container_width=True, hide_index=True)