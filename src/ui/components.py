from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, UnidentifiedImageError

MIN_ZOOM = 25
MAX_ZOOM = 800
ZOOM_STEP = 25
DEFAULT_ZOOM = 100


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


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError):
        return None


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


def render_full_resolution_image(
    image_path: Path,
    caption: str,
    key_prefix: str,
) -> None:
    data_uri = _image_data_uri(image_path)
    dimensions = _image_dimensions(image_path)
    if data_uri is None or dimensions is None:
        st.warning(f"Could not load {image_path.name}")
        return

    width, height = dimensions
    components.html(
        f"""
        <!doctype html>
        <html>
        <head>
        <meta charset="utf-8" />
        <style>
            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                color: #111827;
                background: #ffffff;
            }}

            .sbm-full-resolution-viewer {{
                width: 100%;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                overflow: hidden;
                background: #ffffff;
            }}

            .sbm-full-resolution-toolbar {{
                display: flex;
                align-items: center;
                gap: 8px;
                min-height: 44px;
                padding: 8px;
                border-bottom: 1px solid #d1d5db;
                background: #f9fafb;
            }}

            .sbm-full-resolution-toolbar button {{
                width: 38px;
                height: 32px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background: #ffffff;
                color: #111827;
                cursor: pointer;
                font-size: 18px;
                line-height: 1;
            }}

            .sbm-full-resolution-toolbar button:hover {{
                background: #f3f4f6;
            }}

            .sbm-full-resolution-toolbar input {{
                flex: 1;
                min-width: 140px;
            }}

            .sbm-full-resolution-value {{
                width: 56px;
                text-align: right;
                font-size: 13px;
                color: #374151;
            }}

            .sbm-full-resolution-stage {{
                height: 700px;
                overflow: auto;
                background: #111827;
                padding: 12px;
            }}

            .sbm-full-resolution-image {{
                display: block;
                width: {width}px;
                height: auto;
                max-width: none;
                transform-origin: top left;
                image-rendering: auto;
            }}

            .sbm-full-resolution-caption {{
                padding: 6px 8px;
                border-top: 1px solid #d1d5db;
                color: #4b5563;
                font-size: 12px;
                overflow-wrap: anywhere;
                background: #ffffff;
            }}
        </style>
        </head>
        <body>
        <div class="sbm-full-resolution-viewer">
            <div class="sbm-full-resolution-toolbar">
                <button id="zoomOut" type="button" title="Zoom out">-</button>
                <input
                    id="zoomRange"
                    type="range"
                    min="{MIN_ZOOM}"
                    max="{MAX_ZOOM}"
                    step="{ZOOM_STEP}"
                    value="{DEFAULT_ZOOM}"
                    aria-label="Zoom"
                />
                <button id="zoomIn" type="button" title="Zoom in">+</button>
                <button id="zoomReset" type="button" title="Reset zoom">100</button>
                <span id="zoomValue" class="sbm-full-resolution-value">
                    {DEFAULT_ZOOM}%
                </span>
            </div>
            <div id="stage" class="sbm-full-resolution-stage">
                <img
                    id="fullImage"
                    class="sbm-full-resolution-image"
                    src="{data_uri}"
                    alt="{html.escape(caption)}"
                    width="{width}"
                    height="{height}"
                />
            </div>
            <div class="sbm-full-resolution-caption">{html.escape(caption)}</div>
        </div>
        <script>
            const minZoom = {MIN_ZOOM};
            const maxZoom = {MAX_ZOOM};
            const zoomStep = {ZOOM_STEP};
            const naturalWidth = {width};
            const image = document.getElementById("fullImage");
            const range = document.getElementById("zoomRange");
            const value = document.getElementById("zoomValue");
            const stage = document.getElementById("stage");

            function clampZoom(zoom) {{
                return Math.max(minZoom, Math.min(maxZoom, zoom));
            }}

            function setZoom(nextZoom) {{
                const previousZoom = Number(range.value);
                const zoom = clampZoom(Number(nextZoom));
                const centerX = stage.scrollLeft + stage.clientWidth / 2;
                const centerY = stage.scrollTop + stage.clientHeight / 2;
                const ratio = previousZoom > 0 ? zoom / previousZoom : 1;

                range.value = zoom;
                value.textContent = `${{zoom}}%`;
                image.style.width = `${{Math.round(naturalWidth * zoom / 100)}}px`;

                stage.scrollLeft = centerX * ratio - stage.clientWidth / 2;
                stage.scrollTop = centerY * ratio - stage.clientHeight / 2;
            }}

            document.getElementById("zoomOut").addEventListener("click", () => {{
                setZoom(Number(range.value) - zoomStep);
            }});
            document.getElementById("zoomIn").addEventListener("click", () => {{
                setZoom(Number(range.value) + zoomStep);
            }});
            document.getElementById("zoomReset").addEventListener("click", () => {{
                setZoom(100);
            }});
            range.addEventListener("input", () => {{
                setZoom(range.value);
            }});
            stage.addEventListener("wheel", (event) => {{
                if (!event.ctrlKey) {{
                    return;
                }}
                event.preventDefault();
                const delta = event.deltaY > 0 ? -zoomStep : zoomStep;
                setZoom(Number(range.value) + delta);
            }}, {{ passive: false }});

            setZoom({DEFAULT_ZOOM});
        </script>
        </body>
        </html>
        """,
        height=800,
        scrolling=False,
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
                margin-bottom: 0.75rem;
                overflow: hidden;
            }

            .sbm-hover-zoom-image {
                display: block;
                width: 100%;
                aspect-ratio: 4 / 3;
                object-fit: contain;
                background: #111827;
                border: 1px solid #d1d5db;
                border-radius: 6px;
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
            if st.button(f"View {index + 1}", key=f"{key_prefix}_view_{index}"):
                st.session_state[f"{key_prefix}_zoom"] = str(image_path)

            image = open_image(image_path)
            if image is None:
                st.warning(f"Could not load {image_path.name}")
            else:
                render_hover_zoom_image(
                    image_path,
                    camera_caption(index, image_path),
                )

    zoom_path = st.session_state.get(f"{key_prefix}_zoom")
    if zoom_path:
        st.markdown("### Full Resolution View")
        render_full_resolution_image(
            Path(zoom_path),
            Path(zoom_path).name,
            f"{key_prefix}_full_resolution",
        )
