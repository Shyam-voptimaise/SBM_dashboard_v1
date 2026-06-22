from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
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
DATE_FOLDER_PATTERN = re.compile(
    r"(?x)"
    r"^(?:"
    r"\d{4}[-_.]?\d{2}[-_.]?\d{2}"
    r"|"
    r"\d{2}[-_.]\d{2}[-_.]\d{4}"
    r")$"
)
DATE_FOLDER_FORMATS = (
    "%Y-%m-%d",
    "%Y_%m_%d",
    "%Y.%m.%d",
    "%Y%m%d",
    "%d-%m-%Y",
    "%d_%m_%Y",
    "%d.%m.%Y",
)
COIL_PREFIX_PATTERN = re.compile(r"(?i)^coil[_\-\s]*")
CAMERA_ONLY_PATTERN = re.compile(
    r"(?i)^(?:camera|cam|view|c)[_\-\s]*0?\d+$"
)
MAX_IMAGE_FOLDER_DEPTH = 4


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


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def parse_date_folder_name(name: str) -> date | None:
    if not DATE_FOLDER_PATTERN.match(name):
        return None

    for date_format in DATE_FOLDER_FORMATS:
        try:
            return datetime.strptime(name, date_format).date()
        except ValueError:
            continue
    return None


def _folder_date(path: Path) -> date | None:
    return parse_date_folder_name(path.name)


def _is_date_folder(path: Path) -> bool:
    return _folder_date(path) is not None


def _dedupe_paths(paths: list[Path]) -> tuple[Path, ...]:
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = _safe_resolve(path)
        if resolved in seen:
            continue
        deduped.append(path)
        seen.add(resolved)
    return tuple(deduped)


def _alias_roots(root: Path, aliases: tuple[str, ...]) -> list[Path]:
    roots: list[Path] = []
    for alias in aliases:
        candidate = root / alias
        if candidate.exists() and candidate.is_dir():
            roots.append(candidate)
    return roots


def _date_folders_under(root: Path, capture_date: date | None = None) -> list[Path]:
    folders: list[Path] = []
    for child in _safe_iterdir(root):
        if not child.is_dir():
            continue

        child_date = _folder_date(child)
        if child_date is None:
            continue
        if capture_date is not None and child_date != capture_date:
            continue
        folders.append(child)

    return sorted(
        folders,
        key=lambda path: (_folder_date(path) or date.min, _mtime(path)),
        reverse=True,
    )


def _descendant_tunnel_roots(base_dir: Path, aliases: tuple[str, ...]) -> list[Path]:
    roots: list[Path] = []
    for child in _safe_iterdir(base_dir):
        if not child.is_dir():
            continue
        for alias in aliases:
            candidate = child / alias
            if candidate.exists() and candidate.is_dir():
                roots.append(candidate)
    return sorted(roots, key=_mtime, reverse=True)


def _image_container_folders(root: Path) -> list[Path]:
    folders: list[Path] = []
    queue: list[tuple[Path, int]] = [(root, 0)]
    seen: set[Path] = set()

    while queue:
        current, depth = queue.pop(0)
        resolved = _safe_resolve(current)
        if resolved in seen:
            continue
        seen.add(resolved)

        if _has_images(current):
            folders.append(current)

        if depth >= MAX_IMAGE_FOLDER_DEPTH:
            continue

        subfolders = [
            child
            for child in _safe_iterdir(current)
            if child.is_dir()
        ]
        queue.extend((child, depth + 1) for child in subfolders)

    return folders


def _candidate_tunnel_roots_for_date(
    config: TunnelConfig,
    capture_date: date,
) -> tuple[Path, ...]:
    base_dir = config.base_dir
    if not base_dir.exists() or not base_dir.is_dir():
        return ()

    roots: list[Path] = []
    tunnel_specific = _alias_roots(base_dir, config.aliases)
    for tunnel_root in tunnel_specific:
        if _folder_date(tunnel_root) == capture_date:
            roots.append(tunnel_root)
        roots.extend(_date_folders_under(tunnel_root, capture_date))

    if roots:
        return _dedupe_paths(sorted(roots, key=_mtime, reverse=True))

    date_roots = (
        [base_dir]
        if _folder_date(base_dir) == capture_date
        else _date_folders_under(base_dir, capture_date)
    )
    for date_root in date_roots:
        dated_tunnel_roots = _alias_roots(date_root, config.aliases)
        roots.extend(dated_tunnel_roots or [date_root])

    return _dedupe_paths(sorted(roots, key=_mtime, reverse=True))


def candidate_tunnel_roots(
    config: TunnelConfig,
    capture_date: date | None = None,
) -> tuple[Path, ...]:
    if capture_date is not None:
        return _candidate_tunnel_roots_for_date(config, capture_date)

    base_dir = config.base_dir
    if not base_dir.exists() or not base_dir.is_dir():
        return ()

    tunnel_specific = _alias_roots(base_dir, config.aliases)
    if tunnel_specific:
        return _dedupe_paths(tunnel_specific)

    dated_tunnel_roots = _descendant_tunnel_roots(base_dir, config.aliases)
    if dated_tunnel_roots:
        return _dedupe_paths(dated_tunnel_roots)

    return (base_dir,)


def available_capture_dates(configs: tuple[TunnelConfig, ...]) -> tuple[date, ...]:
    capture_dates: set[date] = set()
    scanned_roots: set[Path] = set()

    for config in configs:
        base_dir = config.base_dir
        if not base_dir.exists() or not base_dir.is_dir():
            continue

        roots = [base_dir, *_alias_roots(base_dir, config.aliases)]
        for root in roots:
            resolved = _safe_resolve(root)
            if resolved in scanned_roots:
                continue
            scanned_roots.add(resolved)

            root_date = _folder_date(root)
            if root_date is not None:
                capture_dates.add(root_date)

            for date_folder in _date_folders_under(root):
                folder_date = _folder_date(date_folder)
                if folder_date is not None:
                    capture_dates.add(folder_date)

    return tuple(sorted(capture_dates, reverse=True))


def discover_coil_folders(
    config: TunnelConfig,
    capture_date: date | None = None,
) -> list[Path]:
    coil_folders: list[Path] = []
    seen: set[Path] = set()

    for root in candidate_tunnel_roots(config, capture_date):
        for folder in _image_container_folders(root):
            resolved = _safe_resolve(folder)
            if resolved in seen:
                continue
            coil_folders.append(folder)
            seen.add(resolved)

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


def _uid_from_coil_folder(coil_folder: Path) -> str:
    folder_name = coil_folder.name
    cleaned = COIL_PREFIX_PATTERN.sub("", folder_name).strip("_-. ")
    if cleaned and not _is_date_folder(coil_folder):
        return cleaned
    return folder_name


def _is_camera_only_uid(uid: str) -> bool:
    return bool(CAMERA_ONLY_PATTERN.match(uid))


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
        if _is_camera_only_uid(uid):
            uid = _uid_from_coil_folder(coil_folder)
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
        fallback_metadata = _group_metadata(latest_images)
        fallback_uid = metadata_uid(fallback_metadata) or _uid_from_coil_folder(
            coil_folder
        )
        groups = [
            _build_group(tunnel, coil_folder, fallback_uid, latest_images, "latest")
        ]

    return sorted(
        groups,
        key=lambda group: group.modified_at or datetime.min,
        reverse=True,
    )


def image_groups_for_tunnel(
    tunnel: str,
    config: TunnelConfig,
    capture_date: date | None = None,
) -> list[ImageGroup]:
    groups: list[ImageGroup] = []
    for coil_folder in discover_coil_folders(config, capture_date):
        groups.extend(image_groups_for_coil(tunnel, coil_folder))

    return sorted(
        groups,
        key=lambda group: group.modified_at or datetime.min,
        reverse=True,
    )
