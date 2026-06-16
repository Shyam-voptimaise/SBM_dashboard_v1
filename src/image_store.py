from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from metadata import load_image_metadata, metadata_uid
from runtime_config import IMAGE_EXTENSIONS, TunnelConfig

EXPLICIT_UID_PATTERN = re.compile(
    r"(?i)(?:uid|frame|capture|image)[_\-\s]*(?:id)?[_\-\s]*([A-Za-z0-9]+(?:[_\-][A-Za-z0-9]+)*)"
)
CAMERA_TOKEN_PATTERN = re.compile(
    r"(?i)(^|[_\-\s.])(?:camera|cam|view|c)[_\-\s]*0?\d+(?=$|[_\-\s.])"
)
NOISE_TOKEN_PATTERN = re.compile(
    r"(?i)(^|[_\-\s.])(?:annot|annotation|defect|boxed|mask)(?=$|[_\-\s.])"
)


@dataclass(frozen=True)
class ImageGroup:
    tunnel: str
    coil: str
    uid: str
    images: tuple[Path, ...]
    coil_folder: Path
    metadata: dict[str, Any]
    annotations: tuple[Path, ...]
    modified_at: datetime | None
    source: str

    @property
    def primary_image(self) -> Path | None:
        return self.images[0] if self.images else None


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def is_annotation_file(path: Path) -> bool:
    return is_image_file(path) and "annot" in path.name.lower()


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


def _has_images(path: Path) -> bool:
    return any(
        is_image_file(child) and not is_annotation_file(child)
        for child in _safe_iterdir(path)
    )


def candidate_tunnel_roots(config: TunnelConfig) -> tuple[Path, ...]:
    base_dir = config.base_dir
    if not base_dir.exists() or not base_dir.is_dir():
        return ()

    tunnel_specific: list[Path] = []
    seen: set[Path] = set()
    for alias in config.aliases:
        candidate = base_dir / alias
        if candidate.exists() and candidate.is_dir() and candidate not in seen:
            tunnel_specific.append(candidate)
            seen.add(candidate)

    if tunnel_specific:
        return tuple(tunnel_specific)

    return (base_dir,)


def discover_coil_folders(config: TunnelConfig) -> list[Path]:
    coil_folders: list[Path] = []
    seen: set[Path] = set()

    for root in candidate_tunnel_roots(config):
        root_coils = [
            child
            for child in _safe_iterdir(root)
            if child.is_dir() and child.name.startswith("coil_")
        ]

        if root_coils:
            for folder in root_coils:
                if folder not in seen:
                    coil_folders.append(folder)
                    seen.add(folder)
        elif _has_images(root):
            coil_folders.append(root)
            seen.add(root)

    return sorted(coil_folders, key=_mtime, reverse=True)


def _image_files_in_coil(coil_folder: Path) -> list[Path]:
    images = [
        child
        for child in _safe_iterdir(coil_folder)
        if is_image_file(child) and not is_annotation_file(child)
    ]
    return sorted(images, key=_mtime, reverse=True)


def _clean_uid_from_stem(stem: str) -> str:
    cleaned = CAMERA_TOKEN_PATTERN.sub("_", stem)
    cleaned = NOISE_TOKEN_PATTERN.sub("_", cleaned)
    cleaned = re.sub(r"[_\-\s.]+", "_", cleaned).strip("_-. ")
    return cleaned or stem


def parse_uid_from_image(image_path: Path, metadata: dict[str, Any]) -> str:
    uid = metadata_uid(metadata)
    if uid:
        return uid

    explicit_match = EXPLICIT_UID_PATTERN.search(image_path.stem)
    if explicit_match:
        return _clean_uid_from_stem(explicit_match.group(1))

    return _clean_uid_from_stem(image_path.stem)


def annotations_for_image(image_path: Path | None) -> tuple[Path, ...]:
    if image_path is None:
        return ()

    folder = image_path.parent
    stem = image_path.stem.lower()
    annotations = [
        child
        for child in _safe_iterdir(folder)
        if is_annotation_file(child)
        and (child.stem.lower().startswith(stem) or stem in child.stem.lower())
    ]
    return tuple(sorted(annotations, key=lambda path: path.name.lower()))


def _group_annotations(images: list[Path]) -> tuple[Path, ...]:
    annotations: list[Path] = []
    seen: set[Path] = set()
    for image in images:
        for annotation in annotations_for_image(image):
            if annotation not in seen:
                annotations.append(annotation)
                seen.add(annotation)
    return tuple(annotations)


def _group_metadata(images: list[Path]) -> dict[str, Any]:
    for image in images:
        metadata = load_image_metadata(image)
        if metadata:
            return metadata
    return {}


def _group_modified_at(images: list[Path], coil_folder: Path) -> datetime | None:
    if images:
        latest = max(images, key=_mtime)
        return _modified_datetime(latest)
    return _modified_datetime(coil_folder)


def _sorted_camera_images(images: list[Path]) -> tuple[Path, ...]:
    return tuple(sorted(images[:4], key=lambda path: path.name.lower()))


def _build_group(
    tunnel: str,
    coil_folder: Path,
    uid: str,
    images: list[Path],
    source: str,
) -> ImageGroup:
    selected_images = list(_sorted_camera_images(images))
    return ImageGroup(
        tunnel=tunnel,
        coil=coil_folder.name,
        uid=uid,
        images=tuple(selected_images),
        coil_folder=coil_folder,
        metadata=_group_metadata(selected_images),
        annotations=_group_annotations(selected_images),
        modified_at=_group_modified_at(selected_images, coil_folder),
        source=source,
    )


def image_groups_for_coil(tunnel: str, coil_folder: Path) -> list[ImageGroup]:
    images = _image_files_in_coil(coil_folder)
    if not images:
        return []

    grouped_images: dict[str, list[Path]] = {}
    for image in images:
        metadata = load_image_metadata(image)
        uid = parse_uid_from_image(image, metadata)
        grouped_images.setdefault(uid, []).append(image)

    confident_groups = {
        uid: group_images
        for uid, group_images in grouped_images.items()
        if len(group_images) >= 2
    }

    if confident_groups:
        groups = [
            _build_group(tunnel, coil_folder, uid, group_images, "grouped")
            for uid, group_images in confident_groups.items()
        ]
    else:
        latest_images = images[:4]
        fallback_uid = latest_images[0].stem
        groups = [
            _build_group(tunnel, coil_folder, fallback_uid, latest_images, "latest")
        ]

    return sorted(
        groups,
        key=lambda group: group.modified_at or datetime.min,
        reverse=True,
    )


def image_groups_for_tunnel(tunnel: str, config: TunnelConfig) -> list[ImageGroup]:
    groups: list[ImageGroup] = []
    for coil_folder in discover_coil_folders(config):
        groups.extend(image_groups_for_coil(tunnel, coil_folder))

    return sorted(
        groups,
        key=lambda group: group.modified_at or datetime.min,
        reverse=True,
    )
