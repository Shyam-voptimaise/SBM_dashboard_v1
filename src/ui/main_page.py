from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from image_store import ImageGroup, available_capture_dates, image_groups_for_tunnel
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
CAPTURE_DATE_KEY = "main_capture_date"
UID_SEARCH_KEY = "main_uid_search"


def _key(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def _coerce_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _compact_search_value(value: object) -> str:
    return "".join(char.lower() for char in str(value) if char.isalnum())


def _group_search_values(group: ImageGroup) -> tuple[str, ...]:
    values = [
        group.uid,
        group.coil,
        group.coil_folder.name,
        str(group.coil_folder),
    ]
    for key in ("coil", "coil_id", "coilId", "uid", "image_uid", "imageUID"):
        value = group.metadata.get(key)
        if value not in (None, ""):
            values.append(str(value))
    return tuple(values)


def _search_rank(group: ImageGroup, query: str) -> int | None:
    query_text = query.strip().lower()
    compact_query = _compact_search_value(query)
    if not query_text:
        return 0

    best_rank: int | None = None
    for value in _group_search_values(group):
        candidate = value.lower()
        compact_candidate = _compact_search_value(value)
        if candidate == query_text or compact_candidate == compact_query:
            rank = 0
        elif candidate.startswith(query_text) or (
            compact_query and compact_candidate.startswith(compact_query)
        ):
            rank = 1
        elif query_text in candidate or (
            compact_query and compact_query in compact_candidate
        ):
            rank = 2
        else:
            continue

        best_rank = rank if best_rank is None else min(best_rank, rank)

    return best_rank


def _group_timestamp(group: ImageGroup) -> float:
    return group.modified_at.timestamp() if group.modified_at else 0.0


def _filter_groups(groups: list[ImageGroup], query: str) -> list[ImageGroup]:
    if not query.strip():
        return groups
    if not _compact_search_value(query):
        return []

    ranked_groups = [
        (rank, group)
        for group in groups
        if (rank := _search_rank(group, query)) is not None
    ]
    return [
        group
        for _, group in sorted(
            ranked_groups,
            key=lambda item: (item[0], -_group_timestamp(item[1])),
        )
    ]


def _groups_for_tunnel(
    tunnel_name: str,
    capture_date: date | None,
) -> list[ImageGroup]:
    return image_groups_for_tunnel(tunnel_name, TUNNELS[tunnel_name], capture_date)


def _render_capture_date_input() -> tuple[date | None, tuple[date, ...]]:
    capture_dates = available_capture_dates(tuple(TUNNELS.values()))
    if not capture_dates:
        st.date_input(
            "Image Date",
            value=date.today(),
            disabled=True,
            key=f"{CAPTURE_DATE_KEY}_disabled",
        )
        return None, capture_dates

    latest_date = capture_dates[0]
    min_date = min(capture_dates)
    max_date = max(capture_dates)
    current_date = _coerce_date(st.session_state.get(CAPTURE_DATE_KEY))
    if current_date is None or current_date < min_date or current_date > max_date:
        st.session_state[CAPTURE_DATE_KEY] = latest_date

    selected_date = st.date_input(
        "Image Date",
        min_value=min_date,
        max_value=max_date,
        key=CAPTURE_DATE_KEY,
    )
    return _coerce_date(selected_date) or latest_date, capture_dates


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


def _empty_group_message(
    tunnel_name: str,
    capture_date: date | None,
    uid_query: str,
) -> str:
    date_text = f" on {capture_date.isoformat()}" if capture_date else ""
    if uid_query.strip():
        return (
            f"No coil images found for {tunnel_name}{date_text} "
            f'matching "{uid_query.strip()}".'
        )
    return f"No coil images found for {tunnel_name}{date_text}."


def _image_fragment_interval(sidebar_state: SidebarState) -> int | None:
    if not sidebar_state.auto_refresh_images:
        return None
    return max(1, int(sidebar_state.image_refresh_seconds))


def _metadata_target_image(group: ImageGroup) -> Path | None:
    for image in group.images:
        if load_image_metadata(image):
            return image
    return group.primary_image


def render_main_page(sidebar_state: SidebarState) -> None:
    @st.fragment(run_every=_image_fragment_interval(sidebar_state))
    def render_live_image_workspace() -> None:
        render_image_workspace(sidebar_state)

    render_live_image_workspace()
    render_stats_section()


def render_image_workspace(sidebar_state: SidebarState) -> None:
    tunnel_column, date_column, search_column = st.columns([1, 1, 1])

    with tunnel_column:
        tunnel_choice = st.selectbox(
            "Tunnel",
            TUNNEL_FILTER_OPTIONS,
            index=0,
            key="main_tunnel_choice",
        )
    with date_column:
        selected_capture_date, capture_dates = _render_capture_date_input()
    with search_column:
        uid_query = st.text_input(
            "UID / Coil Search",
            placeholder="Enter coil id or UID",
            key=UID_SEARCH_KEY,
        ).strip()

    if (
        capture_dates
        and selected_capture_date is not None
        and selected_capture_date not in capture_dates
    ):
        st.warning(
            f"No date folder found for {selected_capture_date.isoformat()}."
        )

    if tunnel_choice == ALL_TUNNELS:
        for tunnel_name in TUNNEL_NAMES:
            groups = _filter_groups(
                _groups_for_tunnel(tunnel_name, selected_capture_date),
                uid_query,
            )
            group = groups[0] if uid_query else _selected_or_latest_group(
                tunnel_name,
                groups,
            )
            render_tunnel_section(
                tunnel_name=tunnel_name,
                group=group,
                sidebar_state=sidebar_state,
                section_key=f"all_{_key(tunnel_name)}",
                show_heading=True,
                empty_message=_empty_group_message(
                    tunnel_name,
                    selected_capture_date,
                    uid_query,
                ),
            )
    else:
        groups = _filter_groups(
            _groups_for_tunnel(tunnel_choice, selected_capture_date),
            uid_query,
        )
        group_identities = [_group_identity(group) for group in groups]
        if uid_query:
            group_options = group_identities
        elif group_identities:
            group_options = [LATEST_GROUP_SELECTION, *group_identities]
        else:
            group_options = []
        groups_by_identity = {_group_identity(group): group for group in groups}
        uid_counts = Counter(group.uid for group in groups)
        selected_group: str | None = None

        with search_column:
            if group_options:
                uid_select_key = f"uid_select_{_key(tunnel_choice)}"
                if st.session_state.get(uid_select_key) not in group_options:
                    st.session_state[uid_select_key] = group_options[0]
                selected_group = st.selectbox(
                    "UID / Coil",
                    group_options,
                    format_func=lambda identity: _uid_option_label(
                        identity,
                        groups_by_identity,
                        uid_counts,
                    ),
                    key=uid_select_key,
                )
                st.session_state[
                    f"selected_group_{_key(tunnel_choice)}"
                ] = selected_group
            else:
                st.selectbox(
                    "UID / Coil",
                    ["No matching UIDs"],
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
            empty_message=_empty_group_message(
                tunnel_choice,
                selected_capture_date,
                uid_query,
            ),
        )

    date_status = (
        selected_capture_date.isoformat()
        if selected_capture_date is not None
        else "all dates"
    )
    search_status = f" | search: {uid_query}" if uid_query else ""
    refresh_status = (
        f"Live image scan: {datetime.now().strftime('%H:%M:%S')} | "
        f"date: {date_status}{search_status} | "
        f"every {sidebar_state.image_refresh_seconds} sec"
        if sidebar_state.auto_refresh_images
        else (
            f"Live image scan: {datetime.now().strftime('%H:%M:%S')} | "
            f"date: {date_status}{search_status} | paused"
        )
    )
    st.caption(refresh_status)


def render_tunnel_section(
    tunnel_name: str,
    group: ImageGroup | None,
    sidebar_state: SidebarState,
    section_key: str,
    show_heading: bool,
    empty_message: str | None = None,
) -> None:
    if show_heading:
        st.subheader(tunnel_name)

    if group is None:
        st.warning(empty_message or f"No coil images found for {tunnel_name}.")
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
