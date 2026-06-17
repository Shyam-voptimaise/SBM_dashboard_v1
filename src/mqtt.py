from __future__ import annotations

import json
import os
import shlex
import socket
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import streamlit as st


class TemperatureState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {
            "value": None,
            "sensor": None,
            "sensor_status": None,
            "source_timestamp": None,
            "updated_at": None,
            "broker": None,
            "connected": False,
            "error": None,
            "raw_payload": None,
        }

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            self._data.update(kwargs)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)


def parse_broker_list(raw_brokers: str, default_port: int) -> list[tuple[str, int]]:
    brokers: list[tuple[str, int]] = []

    for entry in str(raw_brokers).replace(";", ",").split(","):
        entry = entry.strip()
        if not entry:
            continue

        host = entry
        port = default_port

        if entry.count(":") == 1:
            maybe_host, maybe_port = entry.rsplit(":", 1)
            if maybe_host and maybe_port.isdigit():
                host = maybe_host
                port = int(maybe_port)

        brokers.append((host, port))

    return brokers or [("localhost", default_port)]


@dataclass(frozen=True)
class MqttConnectionSettings:
    brokers: str
    topic: str
    port: int
    tls_enabled: bool
    ca_file: str
    command_was_pasted: bool


def _next_option_value(tokens: list[str], index: int) -> str | None:
    next_token = tokens[index + 1] if index + 1 < len(tokens) else None
    if next_token and not next_token.startswith("-"):
        return next_token
    return None


def extract_mqtt_command_values(
    raw_brokers: str,
    current_topic: str,
    current_port: int,
    current_tls_enabled: bool,
    current_ca_file: str,
) -> MqttConnectionSettings:
    text = str(raw_brokers).strip()
    if "mosquitto_sub" not in text:
        return MqttConnectionSettings(
            brokers=text,
            topic=current_topic,
            port=current_port,
            tls_enabled=current_tls_enabled,
            ca_file=current_ca_file,
            command_was_pasted=False,
        )

    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()

    host: str | None = None
    port = current_port
    topic: str | None = None
    ca_file = current_ca_file
    tls_enabled = current_tls_enabled

    for index, token in enumerate(tokens):
        next_token = _next_option_value(tokens, index)

        if token in ("-h", "--host") and next_token:
            host = next_token
        elif token.startswith("-h") and len(token) > 2:
            host = token[2:]
        elif token in ("-p", "--port") and next_token:
            try:
                port = int(next_token)
            except ValueError:
                pass
        elif token.startswith("-p") and len(token) > 2:
            try:
                port = int(token[2:])
            except ValueError:
                pass
        elif token in ("-t", "--topic") and next_token:
            topic = next_token
        elif token.startswith("-t") and len(token) > 2:
            topic = token[2:]
        elif token in ("--cafile", "--capath") and next_token:
            ca_file = next_token
            tls_enabled = True
        elif token.startswith("--cafile="):
            ca_file = token.partition("=")[2]
            tls_enabled = True
        elif token.startswith("--capath="):
            ca_file = token.partition("=")[2]
            tls_enabled = True
        elif token in ("--insecure", "--tls-alpn"):
            tls_enabled = True

    if port == 8883:
        tls_enabled = True

    if not host:
        return MqttConnectionSettings(
            brokers=text,
            topic=current_topic,
            port=current_port,
            tls_enabled=current_tls_enabled,
            ca_file=current_ca_file,
            command_was_pasted=False,
        )

    return MqttConnectionSettings(
        brokers=host,
        topic=topic or current_topic,
        port=port,
        tls_enabled=tls_enabled,
        ca_file=ca_file,
        command_was_pasted=True,
    )


def parse_temperature_payload(payload: str) -> dict[str, Any]:
    try:
        data: Any = json.loads(payload)
    except json.JSONDecodeError:
        data = payload

    if isinstance(data, dict):
        camera = data.get("camera")
        nested_camera = camera if isinstance(camera, dict) else {}
        raw_temp = (
            data.get("temp_c")
            if data.get("temp_c") is not None
            else data.get(
                "temperature_c",
                data.get(
                    "tempC",
                    data.get(
                        "camera_temp_c",
                        data.get(
                            "camera_temperature_c",
                            data.get(
                                "camera_temp",
                                data.get(
                                    "camera_temperature",
                                    data.get(
                                        "temperature",
                                        data.get(
                                            "temp",
                                            nested_camera.get(
                                                "temp_c",
                                                nested_camera.get(
                                                    "temperature",
                                                    nested_camera.get("temp"),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )

        try:
            value = float(raw_temp) if raw_temp is not None else None
        except (TypeError, ValueError):
            value = None

        return {
            "value": value,
            "sensor": data.get("sensor") or data.get("camera_id") or data.get("camera"),
            "sensor_status": data.get("status"),
            "source_timestamp": data.get("timestamp"),
            "raw_payload": payload,
        }

    try:
        value = float(data)
    except (TypeError, ValueError):
        value = None

    return {
        "value": value,
        "sensor": None,
        "sensor_status": None,
        "source_timestamp": None,
        "raw_payload": payload,
    }


def create_mqtt_client(client_id: str) -> mqtt.Client:
    try:
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


def mqtt_success(reason_code: Any) -> bool:
    if reason_code in (0, "0"):
        return True
    if hasattr(reason_code, "is_failure"):
        is_failure = reason_code.is_failure
        return not is_failure() if callable(is_failure) else not is_failure
    return str(reason_code).lower() == "success"


@st.cache_resource(show_spinner=False)
def start_mqtt(
    raw_brokers: str,
    topic: str,
    default_port: int,
    connect_timeout: float,
    tls_enabled: bool,
    ca_file: str,
) -> tuple[TemperatureState, mqtt.Client | None]:
    state = TemperatureState()
    last_error: str | None = None

    for host, port in parse_broker_list(raw_brokers, default_port):
        broker_label = f"{host}:{port}"

        try:
            with socket.create_connection((host, port), timeout=connect_timeout):
                pass
        except socket.gaierror as exc:
            last_error = (
                f"{broker_label} - hostname not found: {exc}. "
                "Use the Pi IP address if the .local name does not resolve."
            )
            continue
        except OSError as exc:
            last_error = f"{broker_label} - {exc}"
            continue

        client = create_mqtt_client(
            f"sbm-dashboard-temp-{os.getpid()}-{host.replace('.', '-')}-{port}"
        )
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        try:
            if tls_enabled:
                ca_path = ca_file.strip()
                ca_certs: str | None = None
                if ca_path and not Path(ca_path).expanduser().exists():
                    last_error = f"{broker_label} - MQTT CA file not found: {ca_path}"
                    continue
                if ca_path:
                    ca_certs = str(Path(ca_path).expanduser())
                client.tls_set(ca_certs=ca_certs)
        except Exception as exc:
            last_error = f"{broker_label} - MQTT TLS setup failed: {exc}"
            continue

        def on_connect(
            client: mqtt.Client,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any = None,
        ) -> None:
            if mqtt_success(reason_code):
                client.subscribe(topic)
                state.update(connected=True, broker=broker_label, error=None)
            else:
                state.update(
                    connected=False,
                    broker=broker_label,
                    error=f"MQTT connect failed: {reason_code}",
                )

        def on_disconnect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
            reason_code = args[1] if len(args) > 1 else args[0] if args else None
            state.update(
                connected=False,
                error=f"MQTT disconnected: {reason_code}",
            )

        def on_message(client: mqtt.Client, userdata: Any, msg: Any) -> None:
            try:
                payload = msg.payload.decode("utf-8")
                reading = parse_temperature_payload(payload)
                state.update(
                    **reading,
                    updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    connected=True,
                    broker=broker_label,
                    error=None,
                )
            except Exception as exc:
                state.update(error=f"MQTT message error: {exc}")

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        try:
            client.connect(host, port, 60)
            client.subscribe(topic)
            client.loop_start()
            state.update(connected=True, broker=broker_label, error=None)
            return state, client
        except Exception as exc:
            last_error = f"{broker_label} - {exc}"
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass

    state.update(
        connected=False,
        error=last_error or "No MQTT broker configured",
    )
    return state, None
