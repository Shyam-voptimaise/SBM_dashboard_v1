from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_CONFIG_PATH = PROJECT_ROOT / "config" / "runtime.yaml"


class RuntimeConfigError(ValueError):
    """Raised when runtime.yaml cannot be parsed into a mapping."""


@dataclass(frozen=True)
class TunnelConfig:
    name: str
    base_dir: Path
    aliases: tuple[str, ...]


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    previous = ""

    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single and previous != "\\":
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return line[:index]
        previous = char

    return line


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in ("", "null", "Null", "NULL", "~"):
        return None
    if value in ("true", "True", "TRUE"):
        return True
    if value in ("false", "False", "FALSE"):
        return False
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def _yaml_tokens(text: str) -> list[tuple[int, str, int]]:
    tokens: list[tuple[int, str, int]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise RuntimeConfigError(
                f"Tabs are not supported in runtime.yaml at line {line_number}."
            )

        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        tokens.append((indent, line.strip(), line_number))

    return tokens


def _parse_block(
    tokens: list[tuple[int, str, int]],
    index: int,
    indent: int,
) -> tuple[Any, int]:
    if index >= len(tokens):
        return {}, index

    is_list = tokens[index][1].startswith("- ")
    if is_list:
        items: list[Any] = []
        while index < len(tokens):
            line_indent, content, line_number = tokens[index]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise RuntimeConfigError(
                    f"Unexpected indentation in runtime.yaml at line {line_number}."
                )
            if not content.startswith("- "):
                break

            value = content[2:].strip()
            index += 1
            if value:
                items.append(_parse_scalar(value))
            elif index < len(tokens) and tokens[index][0] > indent:
                child, index = _parse_block(tokens, index, tokens[index][0])
                items.append(child)
            else:
                items.append(None)

        return items, index

    values: dict[str, Any] = {}
    while index < len(tokens):
        line_indent, content, line_number = tokens[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise RuntimeConfigError(
                f"Unexpected indentation in runtime.yaml at line {line_number}."
            )
        if content.startswith("- "):
            break

        key, separator, raw_value = content.partition(":")
        if not separator:
            raise RuntimeConfigError(
                f"Expected a key/value pair in runtime.yaml at line {line_number}."
            )

        key = str(_parse_scalar(key.strip()))
        raw_value = raw_value.strip()
        index += 1

        if raw_value:
            values[key] = _parse_scalar(raw_value)
        elif index < len(tokens) and tokens[index][0] > indent:
            child, index = _parse_block(tokens, index, tokens[index][0])
            values[key] = child
        else:
            values[key] = None

    return values, index


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    tokens = _yaml_tokens(text)
    if not tokens:
        return {}

    parsed, index = _parse_block(tokens, 0, tokens[0][0])
    if index != len(tokens):
        _, _, line_number = tokens[index]
        raise RuntimeConfigError(
            f"Unexpected content in runtime.yaml at line {line_number}."
        )
    if not isinstance(parsed, dict):
        raise RuntimeConfigError("runtime.yaml must contain a top-level mapping.")

    return parsed


def _load_runtime_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        data = _parse_simple_yaml(text)
    else:
        data = yaml.safe_load(text) or {}

    if not isinstance(data, dict):
        raise RuntimeConfigError("runtime.yaml must contain a top-level mapping.")

    return data


def _runtime_config_path() -> Path:
    configured = os.getenv("SBM_RUNTIME_CONFIG")
    if not configured:
        return DEFAULT_RUNTIME_CONFIG_PATH

    path = Path(configured).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


RUNTIME_CONFIG_PATH = _runtime_config_path()
RUNTIME_CONFIG = _load_runtime_file(RUNTIME_CONFIG_PATH)


def _get(path: tuple[str, ...], default: Any) -> Any:
    value: Any = RUNTIME_CONFIG
    for key in path:
        if not isinstance(value, Mapping):
            return default
        value = value.get(key, default)
    return value


def _as_str(value: Any, default: str) -> str:
    if value in (None, ""):
        return default
    return str(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default

    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "y", "on", "enabled"):
        return True
    if normalized in ("0", "false", "no", "n", "off", "disabled"):
        return False
    return default


def _as_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        items = tuple(str(item) for item in value if item not in (None, ""))
        return items or default
    if value not in (None, ""):
        return (str(value),)
    return default


def _resolve_path(value: Any, default: Path) -> Path:
    raw_value = str(value) if value not in (None, "") else str(default)
    path = Path(raw_value).expanduser()
    if path.is_absolute() or raw_value.startswith(("/", "\\")):
        return path
    return PROJECT_ROOT / path


def _env_path(env_name: str, default: Path) -> Path:
    return _resolve_path(os.getenv(env_name), default)


def _env_int(env_name: str, default: int) -> int:
    return _as_int(os.getenv(env_name), default)


def _env_float(env_name: str, default: float) -> float:
    return _as_float(os.getenv(env_name), default)


def _env_bool(env_name: str, default: bool) -> bool:
    return _as_bool(os.getenv(env_name), default)


def _normalize_env_key(name: str) -> str:
    normalized = "".join(char if char.isalnum() else "_" for char in name.upper())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def _image_extensions() -> tuple[str, ...]:
    extensions = _as_tuple(
        _get(("images", "extensions"), (".jpg", ".jpeg", ".png", ".bmp")),
        (".jpg", ".jpeg", ".png", ".bmp"),
    )
    return tuple(
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in extensions
    )


PAGE_TITLE = _as_str(_get(("app", "page_title"), None), "SBM Defect Dashboard")
APP_TITLE = _as_str(
    _get(("app", "title"), None),
    "Inline Defect Detection Dashboard - SBM",
)
APP_FOOTER = _as_str(
    _get(("app", "footer"), None),
    "SBM Inline Vision System | 2 Tunnel x 4 View Dashboard",
)

REFRESH_INTERVAL = _env_int(
    "SBM_REFRESH_INTERVAL",
    _as_int(_get(("app", "refresh_interval_seconds"), None), 1),
)

IMAGE_BASE_DIR = _env_path(
    "SBM_IMAGE_BASE_DIR",
    _resolve_path(
        _get(("images", "base_dir"), None),
        Path("/home/voptimaise/basler_sensor_photos"),
    ),
)
IMAGE_EXTENSIONS = _image_extensions()

_DEFAULT_TUNNELS: dict[str, dict[str, Any]] = {
    "Tunnel 1": {
        "env": "SBM_TUNNEL_1_DIR",
        "aliases": ("Tunnel 1", "Tunnel_1", "tunnel_1", "tunnel1", "T1", "t1"),
    },
    "Tunnel 2": {
        "env": "SBM_TUNNEL_2_DIR",
        "aliases": ("Tunnel 2", "Tunnel_2", "tunnel_2", "tunnel2", "T2", "t2"),
    },
}


def _build_tunnels() -> dict[str, TunnelConfig]:
    raw_tunnels = _get(("tunnels",), _DEFAULT_TUNNELS)
    if not isinstance(raw_tunnels, Mapping) or not raw_tunnels:
        raw_tunnels = _DEFAULT_TUNNELS

    tunnels: dict[str, TunnelConfig] = {}
    for tunnel_name, raw_config in raw_tunnels.items():
        name = str(tunnel_name)
        config = raw_config if isinstance(raw_config, Mapping) else {}
        default_config = _DEFAULT_TUNNELS.get(name, {})

        env_name = _as_str(
            config.get("env"),
            str(default_config.get("env") or f"SBM_{_normalize_env_key(name)}_DIR"),
        )
        configured_base_dir = _resolve_path(config.get("base_dir"), IMAGE_BASE_DIR)
        aliases = _as_tuple(
            config.get("aliases"),
            _as_tuple(default_config.get("aliases"), (name,)),
        )

        tunnels[name] = TunnelConfig(
            name=name,
            base_dir=_env_path(env_name, configured_base_dir),
            aliases=aliases,
        )

    return tunnels


TUNNELS = _build_tunnels()
TUNNEL_NAMES = tuple(TUNNELS.keys())
ALL_TUNNELS = _as_str(_get(("filters", "all_tunnels_label"), None), "All Tunnels")
TUNNEL_FILTER_OPTIONS = (*TUNNEL_NAMES, ALL_TUNNELS)

SHIFTS = _as_tuple(_get(("operator", "shifts"), None), ("A", "B", "C"))
VALIDATION_DECISIONS = _as_tuple(
    _get(("validation", "decisions"), None),
    ("Not Validated", "Defect Confirmed", "False Alarm"),
)
UNVALIDATED_DECISION = _as_str(
    _get(("validation", "unvalidated_decision"), None),
    VALIDATION_DECISIONS[0],
)

_mqtt_brokers = _get(
    ("mqtt", "brokers"),
    ("localhost", "voptimaipi5.local", "voptimaipi5"),
)
MQTT_BROKERS = os.getenv(
    "MQTT_BROKERS",
    os.getenv("MQTT_BROKER", ",".join(_as_tuple(_mqtt_brokers, ("localhost",)))),
)
MQTT_PORT = _env_int("MQTT_PORT", _as_int(_get(("mqtt", "port"), None), 1883))
MQTT_TOPIC = os.getenv(
    "MQTT_TOPIC",
    _as_str(_get(("mqtt", "topic"), None), "hotmetal/env/reading"),
)
MQTT_TLS_ENABLED = _env_bool(
    "MQTT_TLS_ENABLED",
    _as_bool(_get(("mqtt", "tls_enabled"), None), False),
)
MQTT_CA_FILE = os.getenv(
    "MQTT_CA_FILE",
    _as_str(_get(("mqtt", "ca_file"), None), ""),
)
MQTT_CONNECT_TIMEOUT = _env_float(
    "MQTT_CONNECT_TIMEOUT",
    _as_float(_get(("mqtt", "connect_timeout_seconds"), None), 2.0),
)
