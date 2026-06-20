from __future__ import annotations

from pathlib import Path


class EnhancementDependencyError(RuntimeError):
    """Raised when optional image enhancement dependencies are unavailable."""


def enhance_coil_image(path: Path) -> bytes | None:
    try:
        import cv2 as cv
        import numpy as np
    except ImportError as exc:
        raise EnhancementDependencyError(
            "Image enhancement needs OpenCV. Run `uv sync` to install the dashboard dependencies."
        ) from exc

    try:
        raw_image = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None

    if raw_image.size == 0:
        return None

    img = cv.imdecode(raw_image, cv.IMREAD_GRAYSCALE)
    if img is None:
        return None

    bg = cv.GaussianBlur(img, (0, 0), 45)
    flat = cv.divide(img, bg, scale=255)

    gamma = 0.75
    lut = np.array(
        [((i / 255.0) ** gamma) * 255 for i in range(256)],
        dtype=np.uint8,
    )
    gamma_img = cv.LUT(flat, lut)

    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gamma_img)

    ok, encoded = cv.imencode(".png", enhanced)
    if not ok:
        return None

    return encoded.tobytes()
