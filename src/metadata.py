from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

UID_KEYS = (
    "uid",
    "UID",
    "uid_number",
    "UID_number",
    "uid_no",
    "UID_NO",
    "image_uid",
    "imageUID",
    "coil_uid",
    "coilUID",
    "coil_number",
    "coilNumber",
    "coil_no",
    "coilNo",
    "frame_id",
    "frameID",
    "capture_id",
    "captureID",
)

SHARED_METADATA_FILENAMES = (
    "metadata.json",
    "meta.json",
    "data.json",
    "coil_metadata.json",
)


def _json_files(folder: Path) -> list[Path]:
    try:
        return sorted(folder.glob("*.json"), key=lambda path: path.name.lower())
    except (OSError, PermissionError):
        return []


def metadata_candidates_for_image(image_path: Path) -> tuple[Path, ...]:
    exact_path = image_path.with_suffix(".json")
    candidates: list[Path] = [exact_path]
    seen: set[Path] = {exact_path}

    for file_name in SHARED_METADATA_FILENAMES:
        candidate = image_path.parent / file_name
        if candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)

    image_stem = image_path.stem.lower()
    json_paths = _json_files(image_path.parent)

    for candidate in json_paths:
        candidate_stem = candidate.stem.lower()
        if candidate in seen:
            continue
        if image_stem == candidate_stem:
            candidates.append(candidate)
            seen.add(candidate)

    for candidate in json_paths:
        candidate_stem = candidate.stem.lower()
        if candidate in seen:
            continue
        if image_stem in candidate_stem or candidate_stem in image_stem:
            candidates.append(candidate)
            seen.add(candidate)

    if len(json_paths) == 1 and json_paths[0] not in seen:
        candidates.append(json_paths[0])

    return tuple(candidates)


def metadata_path_for_image(image_path: Path) -> Path:
    for candidate in metadata_candidates_for_image(image_path):
        if candidate.exists():
            return candidate
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

    for candidate in metadata_candidates_for_image(image_path):
        metadata = load_metadata_file(candidate)
        if metadata:
            return metadata

    return {}


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
