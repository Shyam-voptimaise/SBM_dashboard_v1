from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from image_store import parse_date_folder_name
from metadata import parse_datetime

TEMPERATURE_LOG_FILE = "camera_temperature.jsonl"
TAIL_BYTES = 256 * 1024
CAMERA_COUNT = 2

CAMERA_KEYS = (
    "camera_no",
    "camera_number",
    "camera_id",
    "camera",
    "cam_no",
    "cam_number",
    "cam_id",
    "cam",
    "sensor",
    "sensor_id",
    "id",
    "name",
)
TEMPERATURE_KEYS = (
    "temp_c",
    "temperature_c",
    "tempC",
    "camera_temp_c",
    "camera_temperature_c",
    "camera_temp",
    "camera_temperature",
    "temperature",
    "temp",
    "value",
)
STATUS_KEYS = ("status", "state", "health")
TIMESTAMP_KEYS = ("captured_at", "timestamp", "source_timestamp", "created_at")


@dataclass(frozen=True)
class CameraTemperature:
    camera_number: int
    label: str
    value_c: float | None
    status: str | None
    captured_at: datetime | None
    source_path: Path


@dataclass(frozen=True)
class TemperatureSnapshot:
    readings: tuple[CameraTemperature, ...]
    source_path: Path | None = None
    captured_at: datetime | None = None
    updated_at: datetime | None = None
    error: str | None = None


def latest_temperature_snapshot(base_dir: Path) -> TemperatureSnapshot:
    for log_path in _candidate_log_files(base_dir):
        payload = _latest_payload(log_path)
        if payload is None:
            continue

        captured_at = _payload_timestamp(payload)
        readings = _parse_readings(payload, log_path, captured_at)
        return TemperatureSnapshot(
            readings=readings,
            source_path=log_path,
            captured_at=captured_at,
            updated_at=_modified_datetime(log_path),
        )

    return TemperatureSnapshot(readings=())


def over_temperature_readings(
    readings: tuple[CameraTemperature, ...],
    threshold_c: float,
) -> tuple[CameraTemperature, ...]:
    return tuple(
        reading
        for reading in readings
        if reading.value_c is not None and reading.value_c > threshold_c
    )


def _candidate_log_files(base_dir: Path) -> tuple[Path, ...]:
    if not base_dir.exists() or not base_dir.is_dir():
        return ()

    candidates: list[tuple[datetime, float, Path]] = []
    direct_log = base_dir / TEMPERATURE_LOG_FILE
    if direct_log.exists() and direct_log.is_file():
        candidates.append((datetime.min, _mtime(direct_log), direct_log))

    for child in _safe_iterdir(base_dir):
        if not child.is_dir():
            continue

        folder_date = parse_date_folder_name(child.name)
        if folder_date is None:
            continue

        log_path = child / TEMPERATURE_LOG_FILE
        if log_path.exists() and log_path.is_file():
            candidates.append(
                (
                    datetime.combine(folder_date, datetime.min.time()),
                    _mtime(log_path),
                    log_path,
                )
            )

    return tuple(
        path
        for _folder_date, _modified_at, path in sorted(
            candidates,
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )
    )


def _latest_payload(log_path: Path) -> dict[str, Any] | None:
    try:
        with log_path.open("rb") as file:
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(max(0, file_size - TAIL_BYTES))
            chunk = file.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    for raw_line in reversed(chunk.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    return None


def _parse_readings(
    payload: dict[str, Any],
    source_path: Path,
    fallback_captured_at: datetime | None,
) -> tuple[CameraTemperature, ...]:
    raw_readings = payload.get("readings")
    if not isinstance(raw_readings, list):
        raw_readings = [payload]

    readings: list[CameraTemperature] = []
    for index, raw_reading in enumerate(raw_readings[:CAMERA_COUNT], start=1):
        reading = raw_reading if isinstance(raw_reading, dict) else {"value": raw_reading}
        camera_number = _camera_number(reading, index)
        readings.append(
            CameraTemperature(
                camera_number=camera_number,
                label=f"Cam {camera_number}",
                value_c=_temperature_value(reading),
                status=_first_text(reading, STATUS_KEYS),
                captured_at=_payload_timestamp(reading) or fallback_captured_at,
                source_path=source_path,
            )
        )

    return tuple(sorted(readings, key=lambda reading: reading.camera_number))


def _payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in TIMESTAMP_KEYS:
        parsed = parse_datetime(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _camera_number(reading: dict[str, Any], fallback: int) -> int:
    for key in CAMERA_KEYS:
        number = _number_from_value(reading.get(key))
        if number is not None:
            return number

    nested_camera = reading.get("camera")
    if isinstance(nested_camera, dict):
        for key in CAMERA_KEYS:
            number = _number_from_value(nested_camera.get(key))
            if number is not None:
                return number

    return fallback


def _temperature_value(reading: dict[str, Any]) -> float | None:
    for key in TEMPERATURE_KEYS:
        value = _float_value(reading.get(key))
        if value is not None:
            return value

    nested_camera = reading.get("camera")
    if isinstance(nested_camera, dict):
        for key in TEMPERATURE_KEYS:
            value = _float_value(nested_camera.get(key))
            if value is not None:
                return value

    return None


def _first_text(reading: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = reading.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _number_from_value(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _float_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except (OSError, PermissionError):
        return []


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except (OSError, PermissionError):
        return 0.0


def _modified_datetime(path: Path) -> datetime | None:
    timestamp = _mtime(path)
    return datetime.fromtimestamp(timestamp) if timestamp else None
