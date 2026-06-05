from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st
from PIL import Image, UnidentifiedImageError


def render_auto_refresh(interval_seconds: int) -> None:
    st.markdown(
        f"""
        <script>
            setTimeout(function() {{
                window.location.reload();
            }}, {interval_seconds * 1000});
        </script>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(status: str) -> None:
    styles = {
        "Defects detected": ("#991b1b", "#fee2e2", "#fecaca"),
        "No defects": ("#166534", "#dcfce7", "#bbf7d0"),
        "Unknown": ("#374151", "#f3f4f6", "#d1d5db"),
    }
    text_color, background, border = styles.get(status, styles["Unknown"])
    st.markdown(
        f"""
        <div style="
            display:inline-flex;
            align-items:center;
            border:1px solid {border};
            background:{background};
            color:{text_color};
            border-radius:6px;
            padding:0.35rem 0.6rem;
            font-weight:700;">
            {html.escape(status)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def open_image(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as image:
            return image.copy()
    except (OSError, UnidentifiedImageError):
        return None


def camera_caption(index: int, path: Path) -> str:
    match = re.search(r"(?i)(?:camera|cam|view|c)[_\-\s]*0?(\d+)", path.stem)
    camera = f"Camera {match.group(1)}" if match else f"Camera {index + 1}"
    return f"{camera}: {path.name}"


def render_image_grid(images: tuple[Path, ...], key_prefix: str) -> None:
    if not images:
        st.warning("No images found for this UID.")
        return

    if len(images) < 4:
        st.warning(f"Only {len(images)} camera image(s) found for this UID.")

    image_columns = st.columns(4)
    for index in range(4):
        with image_columns[index]:
            if index >= len(images):
                st.empty()
                continue

            image_path = images[index]
            if st.button(f"View {index + 1}", key=f"{key_prefix}_view_{index}"):
                st.session_state[f"{key_prefix}_zoom"] = str(image_path)

            image = open_image(image_path)
            if image is None:
                st.warning(f"Could not load {image_path.name}")
            else:
                st.image(
                    image,
                    caption=camera_caption(index, image_path),
                    use_container_width=True,
                )

    zoom_path = st.session_state.get(f"{key_prefix}_zoom")
    if zoom_path:
        image = open_image(Path(zoom_path))
        if image is not None:
            st.markdown("### Full Resolution View")
            st.image(image, use_container_width=True)
