import streamlit as st
import os
import json
import threading
import time
import socket
import paho.mqtt.client as mqtt
from PIL import Image
from datetime import datetime

# ===================== CONFIG =====================
TUNNELS = {
    "Tunnel 1": {
        "base_dir": "/home/voptimaise/basler_sensor_photos"
    },
    "Tunnel 2": {
        "base_dir": "/home/voptimaise/basler_sensor_photos"
    }
}

REFRESH_INTERVAL = 1  # seconds

# MQTT topic for temperature readings
MQTT_BROKERS = os.getenv(
    "MQTT_BROKERS",
    os.getenv("MQTT_BROKER", "voptimaipi5.local,voptimaipi5,localhost")
)
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "hotmetal/env/reading")
MQTT_CONNECT_TIMEOUT = float(os.getenv("MQTT_CONNECT_TIMEOUT", "2"))


class TemperatureState:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
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

    def update(self, **kwargs):
        with self._lock:
            self._data.update(kwargs)

    def snapshot(self):
        with self._lock:
            return dict(self._data)


def parse_broker_list(raw_brokers, default_port):
    brokers = []

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


def parse_temperature_payload(payload):
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = payload

    if isinstance(data, dict):
        raw_temp = (
            data.get("temp_c")
            if data.get("temp_c") is not None
            else data.get("temperature", data.get("temp"))
        )

        try:
            value = float(raw_temp) if raw_temp is not None else None
        except (TypeError, ValueError):
            value = None

        return {
            "value": value,
            "sensor": data.get("sensor"),
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


def create_mqtt_client(client_id):
    try:
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


def mqtt_success(reason_code):
    if reason_code in (0, "0"):
        return True
    if hasattr(reason_code, "is_failure"):
        is_failure = reason_code.is_failure
        return not is_failure() if callable(is_failure) else not is_failure
    return str(reason_code).lower() == "success"


@st.cache_resource(show_spinner=False)
def start_mqtt(raw_brokers, topic, default_port, connect_timeout):
    state = TemperatureState()
    last_error = None

    for host, port in parse_broker_list(raw_brokers, default_port):
        broker_label = f"{host}:{port}"

        try:
            with socket.create_connection((host, port), timeout=connect_timeout):
                pass
        except OSError as exc:
            last_error = f"{broker_label} - {exc}"
            continue

        client = create_mqtt_client(
            f"sbm-dashboard-temp-{os.getpid()}-{host.replace('.', '-')}-{port}"
        )

        def on_connect(client, userdata, flags, reason_code, properties=None):
            if mqtt_success(reason_code):
                client.subscribe(topic)
                state.update(connected=True, broker=broker_label, error=None)
            else:
                state.update(
                    connected=False,
                    broker=broker_label,
                    error=f"MQTT connect failed: {reason_code}",
                )

        def on_disconnect(client, userdata, *args):
            reason_code = args[0] if args else None
            state.update(
                connected=False,
                error=f"MQTT disconnected: {reason_code}",
            )

        def on_message(client, userdata, msg):
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

# ===================== PAGE =====================
st.set_page_config(page_title="SBM Defect Dashboard", layout="wide")

# ===================== AUTO REFRESH =====================
st.markdown(
    f"""
    <script>
        setTimeout(function() {{
            window.location.reload();
        }}, {REFRESH_INTERVAL * 1000});
    </script>
    """,
    unsafe_allow_html=True
)

# ===================== FUNCTIONS =====================

def get_latest_coil_folder(base_dir):
    if not os.path.exists(base_dir):
        return None

    folders = [
        f for f in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, f)) and f.startswith("coil_")
    ]

    if not folders:
        return None

    folders.sort(
        key=lambda x: os.path.getmtime(os.path.join(base_dir, x)),
        reverse=True
    )

    return os.path.join(base_dir, folders[0])


def get_latest_images(base_dir, count=4):
    coil_folder = get_latest_coil_folder(base_dir)

    if not coil_folder or not os.path.exists(coil_folder):
        return None, []

    images = [
        f for f in os.listdir(coil_folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))
        and "annot" not in f.lower()
    ]

    if not images:
        return coil_folder, []

    images.sort(
        key=lambda x: os.path.getmtime(os.path.join(coil_folder, x)),
        reverse=True
    )

    images = images[:count]
    full_paths = [os.path.join(coil_folder, img) for img in images]

    return coil_folder, sorted(full_paths)


def get_all_annotations(image_path):
    if not image_path:
        return []

    folder = os.path.dirname(image_path)
    base = os.path.splitext(os.path.basename(image_path))[0]

    annots = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.startswith(base) and "annot" in f.lower()
    ]

    return sorted(annots)


def load_meta(image_path):
    if not image_path:
        return {"defects": []}

    meta_path = os.path.splitext(image_path)[0] + ".json"

    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)

    return {"defects": []}


def save_meta(image_path, data):
    meta_path = os.path.splitext(image_path)[0] + ".json"

    with open(meta_path, "w") as f:
        json.dump(data, f, indent=4)


def shift_stats(base_dir):
    stats = {
        "A": {"Defect Confirmed": 0, "False Alarm": 0},
        "B": {"Defect Confirmed": 0, "False Alarm": 0},
        "C": {"Defect Confirmed": 0, "False Alarm": 0}
    }

    if not os.path.exists(base_dir):
        return stats

    for tunnel in os.listdir(base_dir):
        tunnel_path = os.path.join(base_dir, tunnel)

        if not os.path.isdir(tunnel_path):
            continue

        for coil in os.listdir(tunnel_path):
            coil_path = os.path.join(tunnel_path, coil)

            if not os.path.isdir(coil_path):
                continue

            for f in os.listdir(coil_path):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(coil_path, f)) as j:
                            d = json.load(j)
                            sh = d.get("shift")
                            res = d.get("operator_decision")

                            if sh in stats and res in stats[sh]:
                                stats[sh][res] += 1
                    except:
                        continue

    return stats


# ===================== SIDEBAR =====================
st.sidebar.title("Operator Details")
op_name = st.sidebar.text_input("Operator Name")
op_id = st.sidebar.text_input("Operator ID")
shift = st.sidebar.selectbox("Shift", ["A", "B", "C"])

st.sidebar.divider()
st.sidebar.write(f"Auto refresh every {REFRESH_INTERVAL} sec")

# MQTT broker can be the Pi hostname/IP when running this dashboard on a laptop.
st.sidebar.divider()
mqtt_brokers = st.sidebar.text_input(
    "MQTT broker(s)",
    value=MQTT_BROKERS,
    help="Use the Pi hostname or IP when the dashboard runs on a laptop.",
)
mqtt_topic = st.sidebar.text_input("MQTT topic", value=MQTT_TOPIC)

if st.sidebar.button("Reconnect MQTT"):
    start_mqtt.clear()
    st.rerun()

# ensure MQTT subscriber is running and survives Streamlit refreshes
temp_state, _mqtt_client = start_mqtt(
    mqtt_brokers,
    mqtt_topic,
    MQTT_PORT,
    MQTT_CONNECT_TIMEOUT,
)
latest_temp = temp_state.snapshot()
latest_temp["ts"] = latest_temp.get("updated_at")

# show temperature reading in sidebar
with st.sidebar:
    st.markdown("### Temperature")
    temp_display = st.empty()
    ts_display = st.empty()

    val = latest_temp.get("value")
    ts = latest_temp.get("ts")
    sensor_status = latest_temp.get("sensor_status")
    broker = latest_temp.get("broker")
    error = latest_temp.get("error")

    if val is None:
        temp_display.info("No temperature reading yet")
    else:
        temp_display.metric(label="Temperature", value=f"{val:.2f} C")
        if ts:
            ts_display.caption(f"Updated: {ts}")

    if sensor_status:
        st.caption(f"Sensor: {sensor_status}")
    if broker:
        st.caption(f"MQTT: {broker} | {mqtt_topic}")
    if error:
        st.error(error)

# ===================== HEADER =====================
st.title("Inline Defect Detection Dashboard - SBM")
st.divider()

# ===================== MAIN =====================
cols_main = st.columns(2)

for col, (tunnel, cfg) in zip(cols_main, TUNNELS.items()):

    with col:
        st.subheader(tunnel)

        coil_folder, images = get_latest_images(cfg["base_dir"], 4)

        if not coil_folder:
            st.warning("No coil found")
            continue

        st.info(f"📦 Current Coil: {os.path.basename(coil_folder)}")

        if not images:
            st.warning("No images found")
            continue

        # ===================== DEFECT PRIORITY =====================
        first_img = images[0]
        annots = get_all_annotations(first_img)

        if annots:
            st.markdown("### 🚨 Defect Detected")
            for a in annots:
                st.image(Image.open(a), width=700)

        # ===================== THUMBNAILS =====================
        st.markdown("### 4 Camera Views")

        thumb_cols = st.columns(4)

        for i, img in enumerate(images):
            with thumb_cols[i]:
                if st.button(f"View {i+1}", key=f"{tunnel}_{i}"):
                    st.session_state[f"zoom_{tunnel}"] = img

                st.image(Image.open(img), width=140)

        # ===================== FULL RES VIEW =====================
        zoom_key = f"zoom_{tunnel}"
        if zoom_key in st.session_state:
            st.markdown("### 🔍 Full Resolution View")
            st.image(Image.open(st.session_state[zoom_key]), use_column_width=True)

        # ===================== DEFECT DETAILS =====================
        meta = load_meta(first_img)

        st.markdown("### Detected Defects")
        if meta.get("defects"):
            for d in meta["defects"]:
                st.markdown(
                    f"- **{d['type']}** | {d['severity']} | {d.get('confidence','NA')}"
                )
        else:
            st.info("No defect data available")

        # ===================== DECISION =====================
        decision = st.radio(
            f"Final Decision – {tunnel}",
            ["Not Validated", "Defect Confirmed", "False Alarm"],
            key=f"dec_{tunnel}"
        )

        remark = st.text_area(
            f"Remarks – {tunnel}",
            key=f"rem_{tunnel}"
        )

        if st.button(f"Save Decision – {tunnel}"):

            if not op_name or not op_id:
                st.error("Operator details required")

            elif decision == "Not Validated":
                st.error("Please select a decision")

            else:
                meta.update({
                    "operator_name": op_name,
                    "operator_id": op_id,
                    "shift": shift,
                    "operator_decision": decision,
                    "tunnel": tunnel,
                    "remarks": remark,
                    "validated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "coil": os.path.basename(coil_folder)
                })

                save_meta(first_img, meta)
                st.success("Saved successfully")
                st.rerun()

# ===================== STATS =====================
st.divider()
st.subheader("📊 Shift-wise Statistics")

stats = shift_stats("/home/voptimaise/basler_sensor_photos")

st.table({
    "Shift": list(stats.keys()),
    "Defect Confirmed": [v["Defect Confirmed"] for v in stats.values()],
    "False Alarm": [v["False Alarm"] for v in stats.values()],
    "Total": [
        v["Defect Confirmed"] + v["False Alarm"]
        for v in stats.values()
    ]
})

# ===================== FOOTER =====================
st.divider()
st.caption("SBM Inline Vision System | 2 Tunnel × 4 View Dashboard")
