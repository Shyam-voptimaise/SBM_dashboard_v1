from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

UID_KEYS = (
    "uid",
    "UID",
    "image_uid",
    "imageUID",
    "coil_uid",
    "coilUID",
    "frame_id",
    "frameID",
    "capture_id",
    "captureID",
)


def metadata_path_for_image(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def load_metadata_file(meta_path: Path) -> dict[str, Any]:
    try:
        if not meta_path.exists():
            return {}
        with meta_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def load_image_metadata(image_path: Path | None) -> dict[str, Any]:
    if image_path is None:
        return {}
    return load_metadata_file(metadata_path_for_image(image_path))


def save_image_metadata(image_path: Path, data: dict[str, Any]) -> None:
    meta_path = metadata_path_for_image(image_path)
    with meta_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def metadata_uid(metadata: dict[str, Any]) -> str | None:
    for key in UID_KEYS:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)

    nested = metadata.get("metadata")
    if isinstance(nested, dict):
        for key in UID_KEYS:
            value = nested.get(key)
            if value not in (None, ""):
                return str(value)

    return None


def defect_count(metadata: dict[str, Any]) -> int:
    defects = metadata.get("defects")
    if isinstance(defects, list):
        return len(defects)
    if isinstance(defects, dict):
        return len(defects)
    if defects:
        return 1
    return 0


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
