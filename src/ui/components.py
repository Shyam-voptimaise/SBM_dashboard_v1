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
    if interval_seconds <= 0:
        return

    components.html(
        f"""
        <script>
            (() => {{
                const intervalMs = {interval_seconds * 1000};
                window.setInterval(() => {{
                    let parentIsFullscreen = false;
                    try {{
                        parentIsFullscreen = Boolean(window.parent.document.fullscreenElement);
                    }} catch (error) {{
                        parentIsFullscreen = false;
                    }}

                    if (document.fullscreenElement || parentIsFullscreen) {{
                        return;
                    }}

                    window.parent.location.reload();
                }}, intervalMs);
            }})();
        </script>
        """,
        height=0,
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
                <button type="button" class="zoom-reset zoom-action" aria-label="Reset zoom">Fit</button>
                <span class="zoom-spacer"></span>
                <button type="button" class="zoom-fullscreen zoom-action" aria-label="Maximize full resolution view">Maximize</button>
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
                display: flex;
                flex-direction: column;
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
            #{viewer_id} .zoom-action {{
                width: auto;
                min-width: 2.75rem;
                padding: 0 0.65rem;
                font-size: 0.85rem;
            }}
            #{viewer_id} button:hover {{
                background: #f3f4f6;
            }}
            #{viewer_id} .zoom-spacer {{
                flex: 1;
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
            #{viewer_id}:fullscreen {{
                width: 100vw;
                height: 100vh;
                border: 0;
                border-radius: 0;
                background: #111827;
            }}
            #{viewer_id}:fullscreen .zoom-stage {{
                flex: 1;
                height: auto;
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
                const zoomReset = root.querySelector(".zoom-reset");
                const fullscreen = root.querySelector(".zoom-fullscreen");
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

                function renderFullscreenState() {{
                    const isFullscreen = document.fullscreenElement === root;
                    fullscreen.textContent = isFullscreen ? "Exit" : "Maximize";
                    fullscreen.setAttribute(
                        "aria-label",
                        isFullscreen
                            ? "Exit maximized full resolution view"
                            : "Maximize full resolution view"
                    );
                }}

                zoomIn.addEventListener("click", () => update(scale + 0.25));
                zoomOut.addEventListener("click", () => update(scale - 0.25));
                zoomReset.addEventListener("click", () => update(1));
                fullscreen.addEventListener("click", async () => {{
                    try {{
                        if (document.fullscreenElement) {{
                            await document.exitFullscreen();
                        }} else if (root.requestFullscreen) {{
                            await root.requestFullscreen();
                        }}
                    }} catch (error) {{
                        fullscreen.textContent = "Unavailable";
                        window.setTimeout(renderFullscreenState, 1200);
                    }}
                }});
                document.addEventListener("fullscreenchange", renderFullscreenState);
                stage.addEventListener("wheel", (event) => {{
                    event.preventDefault();
                    const step = event.deltaY < 0 ? 0.15 : -0.15;
                    update(scale + step);
                }}, {{ passive: false }});

                render();
                renderFullscreenState();
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

    display_images = images[:4]
    selected_index_key = f"{key_prefix}_view_index"
    legacy_zoom_key = f"{key_prefix}_zoom"
    selected_index = st.session_state.get(selected_index_key)

    if not isinstance(selected_index, int):
        legacy_zoom_path = st.session_state.get(legacy_zoom_key)
        display_image_paths = [str(path) for path in display_images]
        selected_index = (
            display_image_paths.index(legacy_zoom_path)
            if legacy_zoom_path in display_image_paths
            else 0
        )

    if selected_index < 0 or selected_index >= len(display_images):
        selected_index = 0

    image_columns = st.columns(4)
    for index in range(4):
        with image_columns[index]:
            if index >= len(images):
                st.empty()
                continue

            image_path = images[index]
            if st.button(f"View {index + 1}", key=f"{key_prefix}_view_{index}"):
                selected_index = index
                st.session_state[selected_index_key] = selected_index

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

    zoom_path = display_images[selected_index]
    st.session_state[selected_index_key] = selected_index
    st.session_state[legacy_zoom_key] = str(zoom_path)

    if zoom_path:
        try:
            image = open_display_image(zoom_path, enhance_images)
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
                zoom_path.name,
                f"{key_prefix}_{zoom_path.name}_{enhance_images}",
            )
