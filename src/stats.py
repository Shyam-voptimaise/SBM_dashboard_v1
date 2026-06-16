from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from image_store import (
    annotations_for_image,
    discover_coil_folders,
)
from metadata import (
    defect_count,
    load_metadata_file,
    metadata_uid,
    parse_datetime,
)
from runtime_config import (
    ALL_TUNNELS,
    UNVALIDATED_DECISION,
    VALIDATION_DECISIONS,
    TunnelConfig,
)

CoilStatus = Literal["Defects detected", "No defects", "Unknown"]


def get_coil_status(
    meta: dict[str, Any],
    annotations: list[str] | tuple[str, ...],
) -> CoilStatus:
    if annotations:
        return "Defects detected"

    if defect_count(meta) > 0:
        return "Defects detected"

    if meta and "defects" in meta:
        return "No defects"

    return "Unknown"


def _mtime_datetime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, PermissionError):
        return None


def _matching_image_for_metadata(meta_path: Path) -> Path | None:
    for extension in (".jpg", ".jpeg", ".png", ".bmp"):
        candidate = meta_path.with_suffix(extension)
        if candidate.exists():
            return candidate
    return None


def _record_datetime(meta: dict[str, Any], meta_path: Path) -> datetime | None:
    return parse_datetime(meta.get("validated_at")) or _mtime_datetime(meta_path)


def collect_metadata_records(
    tunnels: dict[str, TunnelConfig],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()

    for tunnel_name, config in tunnels.items():
        for coil_folder in discover_coil_folders(config):
            for meta_path in sorted(coil_folder.glob("*.json")):
                if meta_path in seen_paths:
                    continue

                meta = load_metadata_file(meta_path)
                if not meta:
                    continue

                image_path = _matching_image_for_metadata(meta_path)
                annotations = (
                    tuple(str(path) for path in annotations_for_image(image_path))
                    if image_path
                    else ()
                )
                record_datetime = _record_datetime(meta, meta_path)
                inferred_tunnel = str(meta.get("tunnel") or tunnel_name)
                uid = str(meta.get("uid") or metadata_uid(meta) or meta_path.stem)

                records.append(
                    {
                        "Tunnel": inferred_tunnel,
                        "Coil": str(meta.get("coil") or coil_folder.name),
                        "UID": uid,
                        "Status": get_coil_status(meta, annotations),
                        "Operator Decision": str(
                            meta.get("operator_decision") or UNVALIDATED_DECISION
                        ),
                        "Shift": str(meta.get("shift") or ""),
                        "Validated At": (
                            record_datetime.strftime("%Y-%m-%d %H:%M:%S")
                            if record_datetime
                            else ""
                        ),
                        "Defect Count": defect_count(meta),
                        "_date": record_datetime.date() if record_datetime else None,
                    }
                )
                seen_paths.add(meta_path)

    return sorted(
        records,
        key=lambda record: record.get("Validated At") or "",
        reverse=True,
    )


def filter_records(
    records: list[dict[str, Any]],
    tunnel: str,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for record in records:
        record_date = record.get("_date")
        if tunnel != ALL_TUNNELS and record.get("Tunnel") != tunnel:
            continue
        if record_date and record_date < from_date:
            continue
        if record_date and record_date > to_date:
            continue
        filtered.append(record)
    return filtered


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    display_records = [
        {key: value for key, value in record.items() if not key.startswith("_")}
        for record in records
    ]
    columns = [
        "Tunnel",
        "Coil",
        "UID",
        "Status",
        "Operator Decision",
        "Shift",
        "Validated At",
        "Defect Count",
    ]
    return pd.DataFrame(display_records, columns=columns)


def summary_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    status_counts = Counter(record.get("Status") for record in records)
    decision_counts = Counter(record.get("Operator Decision") for record in records)

    summary = {
        "Total records": len(records),
        "Defects detected": status_counts["Defects detected"],
        "No defects": status_counts["No defects"],
        "Unknown": status_counts["Unknown"],
    }

    for decision in VALIDATION_DECISIONS:
        if decision != UNVALIDATED_DECISION:
            summary[decision] = decision_counts[decision]

    return summary
