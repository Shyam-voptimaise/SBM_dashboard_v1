from __future__ import annotations

import base64
import html
import io
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, UnidentifiedImageError

from image_enhancement import EnhancementDependencyError, enhance_coil_image


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


def _modified_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(show_spinner=False)
def _cached_enhanced_image(path_text: str, modified_ns: int) -> bytes | None:
    _ = modified_ns
    return enhance_coil_image(Path(path_text))


def open_display_image(path: Path, enhance_images: bool) -> Image.Image | bytes | None:
    if not enhance_images:
        return open_image(path)
    return _cached_enhanced_image(str(path), _modified_ns(path))


def camera_caption(index: int, path: Path) -> str:
    match = re.search(r"(?i)(?:camera|cam|view|c)[_\-\s]*0?(\d+)", path.stem)
    camera = f"Camera {match.group(1)}" if match else f"Camera {index + 1}"
    return f"{camera}: {path.name}"


def _caption(index: int, path: Path, enhance_images: bool) -> str:
    caption = camera_caption(index, path)
    if enhance_images:
        return f"Enhanced - {caption}"
    return caption


def _image_png_bytes(image: Image.Image | bytes) -> bytes:
    if isinstance(image, bytes):
        return image

    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def _image_data_url(image: Image.Image | bytes) -> str:
    encoded = base64.b64encode(_image_png_bytes(image)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _dom_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


def render_zoomable_image(
    image: Image.Image | bytes,
    caption: str,
    key_prefix: str,
) -> None:
    viewer_id = f"zoom_viewer_{_dom_id(key_prefix)}"
    data_url = html.escape(_image_data_url(image), quote=True)
    safe_caption = html.escape(caption)
    components.html(
        f"""
        <div id="{viewer_id}" class="zoom-viewer">
            <div class="zoom-toolbar">
                <button type="button" class="zoom-out" aria-label="Zoom out">-</button>
                <span class="zoom-level">100%</span>
                <button type="button" class="zoom-in" aria-label="Zoom in">+</button>
            </div>
            <div class="zoom-stage" tabindex="0">
                <img src="{data_url}" alt="{safe_caption}" draggable="false">
            </div>
            <div class="zoom-caption">{safe_caption}</div>
        </div>
        <style>
            #{viewer_id} {{
                border: 1px solid #d1d5db;
                border-radius: 6px;
                overflow: hidden;
                background: #f9fafb;
                font-family: sans-serif;
            }}
            #{viewer_id} .zoom-toolbar {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                padding: 0.5rem;
                border-bottom: 1px solid #d1d5db;
                background: #ffffff;
            }}
            #{viewer_id} button {{
                width: 2rem;
                height: 2rem;
                border: 1px solid #9ca3af;
                border-radius: 6px;
                background: #ffffff;
                color: #111827;
                font-size: 1.2rem;
                font-weight: 700;
                line-height: 1;
                cursor: pointer;
            }}
            #{viewer_id} button:hover {{
                background: #f3f4f6;
            }}
            #{viewer_id} .zoom-level {{
                min-width: 3.5rem;
                color: #374151;
                font-size: 0.9rem;
                font-weight: 700;
                text-align: center;
            }}
            #{viewer_id} .zoom-stage {{
                height: 680px;
                overflow: auto;
                display: flex;
                align-items: flex-start;
                justify-content: center;
                padding: 1rem;
                background: #111827;
                outline: none;
            }}
            #{viewer_id} img {{
                display: block;
                width: 100%;
                max-width: none;
                height: auto;
                margin: 0 auto;
                transition: width 120ms ease;
                user-select: none;
            }}
            #{viewer_id} .zoom-caption {{
                padding: 0.5rem;
                color: #4b5563;
                font-size: 0.85rem;
                background: #ffffff;
                border-top: 1px solid #d1d5db;
            }}
        </style>
        <script>
            (() => {{
                const root = document.getElementById("{viewer_id}");
                if (!root) return;

                const stage = root.querySelector(".zoom-stage");
                const image = root.querySelector("img");
                const level = root.querySelector(".zoom-level");
                const zoomIn = root.querySelector(".zoom-in");
                const zoomOut = root.querySelector(".zoom-out");
                let scale = 1;

                function clamp(value) {{
                    return Math.min(6, Math.max(0.25, value));
                }}

                function render() {{
                    image.style.width = `${{scale * 100}}%`;
                    level.textContent = `${{Math.round(scale * 100)}}%`;
                }}

                function update(nextScale) {{
                    scale = clamp(nextScale);
                    render();
                }}

                zoomIn.addEventListener("click", () => update(scale + 0.25));
                zoomOut.addEventListener("click", () => update(scale - 0.25));
                stage.addEventListener("wheel", (event) => {{
                    event.preventDefault();
                    const step = event.deltaY < 0 ? 0.15 : -0.15;
                    update(scale + step);
                }}, {{ passive: false }});

                render();
            }})();
        </script>
        """,
        height=780,
        scrolling=False,
    )


def render_image_grid(
    images: tuple[Path, ...],
    key_prefix: str,
    enhance_images: bool = False,
) -> None:
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

            try:
                image = open_display_image(image_path, enhance_images)
            except EnhancementDependencyError as exc:
                st.error(str(exc))
                return

            if image is None:
                action = "enhance" if enhance_images else "load"
                st.warning(f"Could not {action} {image_path.name}")
            else:
                st.image(
                    image,
                    caption=_caption(index, image_path, enhance_images),
                    use_container_width=True,
                )

    zoom_path = st.session_state.get(f"{key_prefix}_zoom")
    if zoom_path:
        try:
            image = open_display_image(Path(zoom_path), enhance_images)
        except EnhancementDependencyError as exc:
            st.error(str(exc))
            return

        if image is not None:
            title = (
                "### Full Resolution Enhanced View"
                if enhance_images
                else "### Full Resolution View"
            )
            st.markdown(title)
            render_zoomable_image(
                image,
                Path(zoom_path).name,
                f"{key_prefix}_{Path(zoom_path).name}_{enhance_images}",
            )