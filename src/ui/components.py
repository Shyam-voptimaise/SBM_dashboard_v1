from __future__ import annotations

import base64
import html
import mimetypes
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


def _image_data_uri(path: Path) -> str | None:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None

    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime_type};base64,{encoded}"


def render_hover_zoom_image(
    image_path: Path,
    caption: str,
    zoom_origin: str = "center center",
) -> None:
    data_uri = _image_data_uri(image_path)
    if data_uri is None:
        st.warning(f"Could not load {image_path.name}")
        return

    st.markdown(
        f"""
        <div
            class="sbm-hover-zoom-frame"
            style="--sbm-zoom-origin: {html.escape(zoom_origin)};"
        >
            <img
                class="sbm-hover-zoom-image"
                src="{data_uri}"
                alt="{html.escape(caption)}"
            />
            <div class="sbm-hover-zoom-caption">{html.escape(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_image_grid(images: tuple[Path, ...], key_prefix: str) -> None:
    if not images:
        st.warning("No images found for this UID.")
        return

    st.markdown(
        """
        <style>
            .sbm-hover-zoom-frame {
                position: relative;
                isolation: isolate;
                z-index: 1;
                margin-bottom: 0.75rem;
                overflow: visible;
            }

            .sbm-hover-zoom-frame:hover {
                z-index: 1000;
            }

            .sbm-hover-zoom-image {
                display: block;
                width: 100%;
                aspect-ratio: 4 / 3;
                object-fit: contain;
                background: #111827;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                transition:
                    transform 120ms ease,
                    box-shadow 120ms ease;
                transform-origin: var(--sbm-zoom-origin, center center);
                cursor: zoom-in;
            }

            .sbm-hover-zoom-frame:hover .sbm-hover-zoom-image {
                transform: scale(2);
                box-shadow: 0 16px 42px rgba(17, 24, 39, 0.32);
            }

            .sbm-hover-zoom-caption {
                color: #4b5563;
                font-size: 0.8rem;
                line-height: 1.25;
                margin-top: 0.35rem;
                overflow-wrap: anywhere;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if len(images) < 4:
        st.warning(f"Only {len(images)} camera image(s) found for this UID.")

    image_columns = st.columns(4)
    for index in range(4):
        with image_columns[index]:
            if index >= len(images):
                st.empty()
                continue

            image_path = images[index]
            zoom_origin = (
                "left center"
                if index == 0
                else "right center"
                if index == 3
                else "center center"
            )
            if st.button(f"View {index + 1}", key=f"{key_prefix}_view_{index}"):
                st.session_state[f"{key_prefix}_zoom"] = str(image_path)

            image = open_image(image_path)
            if image is None:
                st.warning(f"Could not load {image_path.name}")
            else:
                render_hover_zoom_image(
                    image_path,
                    camera_caption(index, image_path),
                    zoom_origin,
                )

    zoom_path = st.session_state.get(f"{key_prefix}_zoom")
    if zoom_path:
        image = open_image(Path(zoom_path))
        if image is not None:
            st.markdown("### Full Resolution View")
            st.image(image, use_container_width=True)
