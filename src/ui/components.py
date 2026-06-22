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
                <button type="button" class="zoom-out" aria-label="Zoom out" title="Zoom out">-</button>
                <div class="zoom-slider-wrap">
                    <span class="zoom-boundary">25%</span>
                    <input class="zoom-slider" type="range" min="25" max="2000" step="25" value="100" aria-label="Zoom percentage">
                    <span class="zoom-boundary">2000%</span>
                </div>
                <span class="zoom-level">100%</span>
                <button type="button" class="zoom-in" aria-label="Zoom in" title="Zoom in">+</button>
                <button type="button" class="zoom-fit" aria-label="Fit image to viewer" title="Fit image to viewer">Fit</button>
                <button type="button" class="zoom-actual" aria-label="Show actual image pixels" title="Show actual image pixels">1:1</button>
                <button type="button" class="zoom-max" aria-label="Zoom to 2000 percent" title="Zoom to 2000 percent">Max</button>
                <span class="zoom-spacer"></span>
                <button type="button" class="zoom-maximize" aria-label="Maximize full resolution view" title="Maximize full resolution view">Full</button>
            </div>
            <div class="zoom-stage" tabindex="0">
                <div class="zoom-canvas">
                    <img src="{data_url}" alt="{safe_caption}" draggable="false">
                </div>
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
                flex-wrap: wrap;
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
            #{viewer_id} button:disabled {{
                color: #9ca3af;
                cursor: not-allowed;
                background: #f9fafb;
            }}
            #{viewer_id} .zoom-slider-wrap {{
                display: flex;
                align-items: center;
                gap: 0.4rem;
                flex: 1 1 18rem;
                min-width: 14rem;
            }}
            #{viewer_id} .zoom-slider {{
                width: 100%;
                min-width: 8rem;
                accent-color: #2563eb;
                cursor: pointer;
            }}
            #{viewer_id} .zoom-boundary {{
                color: #6b7280;
                font-size: 0.78rem;
                font-weight: 700;
                white-space: nowrap;
            }}
            #{viewer_id} .zoom-spacer {{
                flex: 1;
            }}
            #{viewer_id} .zoom-fit,
            #{viewer_id} .zoom-actual,
            #{viewer_id} .zoom-max,
            #{viewer_id} .zoom-maximize {{
                width: auto;
                min-width: 2.75rem;
                padding: 0 0.65rem;
                font-size: 0.85rem;
            }}
            #{viewer_id} .zoom-level {{
                min-width: 4.25rem;
                color: #374151;
                font-size: 0.9rem;
                font-weight: 700;
                text-align: center;
            }}
            #{viewer_id} .zoom-stage {{
                height: 680px;
                overflow: auto;
                position: relative;
                background: #111827;
                outline: none;
                cursor: grab;
                overscroll-behavior: contain;
                touch-action: none;
            }}
            #{viewer_id} .zoom-stage.is-panning {{
                cursor: grabbing;
            }}
            #{viewer_id} .zoom-stage:focus {{
                box-shadow: inset 0 0 0 2px #60a5fa;
            }}
            #{viewer_id} .zoom-canvas {{
                position: relative;
                min-width: 100%;
                min-height: 100%;
            }}
            #{viewer_id} img {{
                display: block;
                position: absolute;
                top: 0;
                left: 0;
                max-width: none;
                transform-origin: top left;
                will-change: transform;
                user-select: none;
                pointer-events: none;
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
                const canvas = root.querySelector(".zoom-canvas");
                const image = root.querySelector("img");
                const level = root.querySelector(".zoom-level");
                const slider = root.querySelector(".zoom-slider");
                const zoomIn = root.querySelector(".zoom-in");
                const zoomOut = root.querySelector(".zoom-out");
                const zoomFit = root.querySelector(".zoom-fit");
                const zoomActual = root.querySelector(".zoom-actual");
                const zoomMax = root.querySelector(".zoom-max");
                const maximize = root.querySelector(".zoom-maximize");
                const minZoom = 0.25;
                const maxZoom = 20;
                let zoom = 1;
                let imageWidth = 1;
                let imageHeight = 1;
                let imageOffsetX = 0;
                let imageOffsetY = 0;
                let isPanning = false;
                let panStartX = 0;
                let panStartY = 0;
                let panScrollLeft = 0;
                let panScrollTop = 0;

                function clampZoom(value) {{
                    return Math.min(maxZoom, Math.max(minZoom, value));
                }}

                function zoomPercent(value) {{
                    return Math.round(value * 100);
                }}

                function layoutImage() {{
                    const scaledWidth = imageWidth * zoom;
                    const scaledHeight = imageHeight * zoom;
                    const canvasWidth = Math.max(stage.clientWidth, scaledWidth);
                    const canvasHeight = Math.max(stage.clientHeight, scaledHeight);

                    imageOffsetX = Math.max(0, (canvasWidth - scaledWidth) / 2);
                    imageOffsetY = Math.max(0, (canvasHeight - scaledHeight) / 2);

                    canvas.style.width = `${{canvasWidth}}px`;
                    canvas.style.height = `${{canvasHeight}}px`;
                    image.style.width = `${{imageWidth}}px`;
                    image.style.height = `${{imageHeight}}px`;
                    image.style.left = `${{imageOffsetX}}px`;
                    image.style.top = `${{imageOffsetY}}px`;
                    image.style.transform = `scale(${{zoom}})`;
                }}

                function syncControls() {{
                    const percent = zoomPercent(zoom);
                    level.textContent = `${{percent}}%`;
                    slider.value = String(percent);
                    zoomOut.disabled = zoom <= minZoom + 0.001;
                    zoomIn.disabled = zoom >= maxZoom - 0.001;
                    zoomMax.disabled = zoom >= maxZoom - 0.001;
                }}

                function imagePointFromStage(anchorX, anchorY) {{
                    return {{
                        x: (stage.scrollLeft + anchorX - imageOffsetX) / zoom,
                        y: (stage.scrollTop + anchorY - imageOffsetY) / zoom,
                    }};
                }}

                function scrollToImagePoint(point, anchorX, anchorY) {{
                    stage.scrollLeft = point.x * zoom + imageOffsetX - anchorX;
                    stage.scrollTop = point.y * zoom + imageOffsetY - anchorY;
                }}

                function viewportAnchor(anchor) {{
                    if (anchor) return anchor;
                    return {{
                        x: stage.clientWidth / 2,
                        y: stage.clientHeight / 2,
                    }};
                }}

                function updateZoom(nextZoom, anchor) {{
                    const target = clampZoom(nextZoom);
                    const pointAnchor = viewportAnchor(anchor);
                    const imagePoint = imagePointFromStage(pointAnchor.x, pointAnchor.y);

                    zoom = target;
                    layoutImage();
                    syncControls();
                    scrollToImagePoint(imagePoint, pointAnchor.x, pointAnchor.y);
                }}

                function zoomStep(direction) {{
                    const percent = zoomPercent(zoom);
                    const step =
                        percent < 100 ? 25 :
                        percent < 400 ? 50 :
                        percent < 1000 ? 100 :
                        250;
                    updateZoom((percent + direction * step) / 100);
                }}

                function fitZoom() {{
                    return clampZoom(Math.min(
                        stage.clientWidth / imageWidth,
                        stage.clientHeight / imageHeight
                    ));
                }}

                function centerImage() {{
                    stage.scrollLeft = Math.max(0, (canvas.scrollWidth - stage.clientWidth) / 2);
                    stage.scrollTop = Math.max(0, (canvas.scrollHeight - stage.clientHeight) / 2);
                }}

                function renderMaximizeState() {{
                    const maximized = document.fullscreenElement === root;
                    maximize.textContent = maximized ? "Exit" : "Full";
                    maximize.setAttribute(
                        "aria-label",
                        maximized
                            ? "Exit maximized full resolution view"
                            : "Maximize full resolution view"
                    );
                }}

                zoomIn.addEventListener("click", () => zoomStep(1));
                zoomOut.addEventListener("click", () => zoomStep(-1));
                zoomFit.addEventListener("click", () => {{
                    updateZoom(fitZoom());
                    centerImage();
                }});
                zoomActual.addEventListener("click", () => updateZoom(1));
                zoomMax.addEventListener("click", () => updateZoom(maxZoom));
                slider.addEventListener("input", () => updateZoom(Number(slider.value) / 100));
                maximize.addEventListener("click", async () => {{
                    try {{
                        if (document.fullscreenElement === root) {{
                            await document.exitFullscreen();
                        }} else if (root.requestFullscreen) {{
                            await root.requestFullscreen();
                        }}
                    }} catch (error) {{
                        maximize.textContent = "Unavailable";
                        window.setTimeout(renderMaximizeState, 1200);
                    }}
                }});
                document.addEventListener("fullscreenchange", () => {{
                    renderMaximizeState();
                    window.setTimeout(() => {{
                        layoutImage();
                        centerImage();
                    }}, 60);
                }});
                stage.addEventListener("wheel", (event) => {{
                    event.preventDefault();
                    const bounds = stage.getBoundingClientRect();
                    const anchor = {{
                        x: event.clientX - bounds.left,
                        y: event.clientY - bounds.top,
                    }};
                    const wheelScale = Math.exp(-event.deltaY * 0.0015);
                    updateZoom(zoom * wheelScale, anchor);
                }}, {{ passive: false }});

                stage.addEventListener("pointerdown", (event) => {{
                    if (event.button !== 0) return;
                    isPanning = true;
                    panStartX = event.clientX;
                    panStartY = event.clientY;
                    panScrollLeft = stage.scrollLeft;
                    panScrollTop = stage.scrollTop;
                    stage.classList.add("is-panning");
                    stage.setPointerCapture(event.pointerId);
                }});
                stage.addEventListener("pointermove", (event) => {{
                    if (!isPanning) return;
                    stage.scrollLeft = panScrollLeft - (event.clientX - panStartX);
                    stage.scrollTop = panScrollTop - (event.clientY - panStartY);
                }});
                stage.addEventListener("pointerup", (event) => {{
                    isPanning = false;
                    stage.classList.remove("is-panning");
                    if (stage.hasPointerCapture(event.pointerId)) {{
                        stage.releasePointerCapture(event.pointerId);
                    }}
                }});
                stage.addEventListener("pointercancel", () => {{
                    isPanning = false;
                    stage.classList.remove("is-panning");
                }});
                stage.addEventListener("keydown", (event) => {{
                    if (event.key === "+" || event.key === "=") {{
                        event.preventDefault();
                        zoomStep(1);
                    }} else if (event.key === "-") {{
                        event.preventDefault();
                        zoomStep(-1);
                    }} else if (event.key === "0") {{
                        event.preventDefault();
                        updateZoom(1);
                    }} else if (event.key === "Home") {{
                        event.preventDefault();
                        updateZoom(minZoom);
                    }} else if (event.key === "End") {{
                        event.preventDefault();
                        updateZoom(maxZoom);
                    }}
                }});
                window.addEventListener("resize", () => {{
                    layoutImage();
                    syncControls();
                }});

                image.addEventListener("load", () => {{
                    imageWidth = image.naturalWidth || 1;
                    imageHeight = image.naturalHeight || 1;
                    zoom = 1;
                    layoutImage();
                    syncControls();
                    centerImage();
                }}, {{ once: true }});
                if (image.complete) {{
                    imageWidth = image.naturalWidth || 1;
                    imageHeight = image.naturalHeight || 1;
                    layoutImage();
                    syncControls();
                    centerImage();
                }} else {{
                    syncControls();
                }}
                renderMaximizeState();
            }})();
        </script>
        """,
        height=820,
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
    zoom_key = f"{key_prefix}_zoom"
    display_image_paths = [str(path) for path in display_images]
    if st.session_state.get(zoom_key) not in display_image_paths:
        st.session_state[zoom_key] = display_image_paths[0]

    image_columns = st.columns(4)
    for index in range(4):
        with image_columns[index]:
            if index >= len(display_images):
                st.empty()
                continue

            image_path = display_images[index]
            if st.button(f"View {index + 1}", key=f"{key_prefix}_view_{index}"):
                st.session_state[zoom_key] = str(image_path)

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

    zoom_path = st.session_state.get(zoom_key)
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
