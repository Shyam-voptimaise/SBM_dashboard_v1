from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PAGE_TITLE = "SBM Defect Dashboard"
APP_TITLE = "Inline Defect Detection Dashboard - SBM"

REFRESH_INTERVAL = int(os.getenv("SBM_REFRESH_INTERVAL", "1"))

IMAGE_BASE_DIR = Path(
    os.getenv("SBM_IMAGE_BASE_DIR", "/home/voptimaise/basler_sensor_photos")
)


@dataclass(frozen=True)
class TunnelConfig:
    name: str
    base_dir: Path
    aliases: tuple[str, ...]


def _path_from_env(env_name: str, default: Path) -> Path:
    return Path(os.getenv(env_name, str(default)))


TUNNELS: dict[str, TunnelConfig] = {
    "Tunnel 1": TunnelConfig(
        name="Tunnel 1",
        base_dir=_path_from_env("SBM_TUNNEL_1_DIR", IMAGE_BASE_DIR),
        aliases=("Tunnel 1", "Tunnel_1", "tunnel_1", "tunnel1", "T1", "t1"),
    ),
    "Tunnel 2": TunnelConfig(
        name="Tunnel 2",
        base_dir=_path_from_env("SBM_TUNNEL_2_DIR", IMAGE_BASE_DIR),
        aliases=("Tunnel 2", "Tunnel_2", "tunnel_2", "tunnel2", "T2", "t2"),
    ),
}

TUNNEL_NAMES = tuple(TUNNELS.keys())
ALL_TUNNELS = "All Tunnels"
TUNNEL_FILTER_OPTIONS = (*TUNNEL_NAMES, ALL_TUNNELS)

# MQTT topic for temperature readings.
MQTT_BROKERS = os.getenv(
    "MQTT_BROKERS",
    os.getenv("MQTT_BROKER", "localhost,voptimaipi5.local,voptimaipi5"),
)
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "hotmetal/env/reading")
MQTT_CONNECT_TIMEOUT = float(os.getenv("MQTT_CONNECT_TIMEOUT", "2"))
