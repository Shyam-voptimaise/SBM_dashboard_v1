import streamlit as st
import os
import json
from PIL import Image
from datetime import datetime
from typing import Dict, Any

# 🔹 NEW IMPORTS
import cv2

try:
    from gpiozero import DigitalOutputDevice
    GPIO_AVAILABLE = True
except:
    GPIO_AVAILABLE = False

# ===================== CONFIG =====================
TUNNELS = {
    "Tunnel 1": {
        "image_dir": r"C:\Users\Abhishek\Downloads\Projects\SBM\Images\19-11-25",
        "annot_dir": r"C:\Users\Abhishek\Downloads\Projects\SBM\Images\Defects\tunnel1"
    },
    "Tunnel 2": {
        "image_dir": r"C:\Users\Abhishek\Downloads\Projects\SBM\Images\10-11-25",
        "annot_dir": r"C:\Users\Abhishek\Downloads\Projects\SBM\Images\Defects\tunnel2"
    }
}

SHUTTER_PIN = 17

if GPIO_AVAILABLE:
    shutter = DigitalOutputDevice(SHUTTER_PIN)

IMAGE_W = 260
ANNOT_W = 260
ZOOM_W = 650

st.set_page_config(page_title="SBM Defect Dashboard", layout="wide")

# ===================== FUNCTIONS =====================

def trigger_shutter():
    if GPIO_AVAILABLE:
        import time
        shutter.on()
        time.sleep(0.2)
        shutter.off()
    else:
        st.warning("GPIO not available")

def get_latest_image(folder, refresh_flag):
    if not refresh_flag:
        return st.session_state.get(f"cached_{folder}")

    images = [
        f for f in os.listdir(folder)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if not images:
        return None

    images.sort(key=lambda x: os.path.getmtime(os.path.join(folder, x)), reverse=True)
    img = os.path.join(folder, images[0])
    st.session_state[f"cached_{folder}"] = img
    return img

def get_all_annotations(annot_dir, image_path):
    if not os.path.exists(annot_dir):
        return []

    base_name = os.path.splitext(os.path.basename(image_path))[0]

    return [
        os.path.join(annot_dir, f)
        for f in os.listdir(annot_dir)
        if f.startswith(base_name)
    ]

def load_meta(image_path) -> Dict[str, Any]:
    meta_path = os.path.splitext(image_path)[0] + ".json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)
    return {"defects": []}

def save_meta(image_path, data: Dict[str, Any]):
    meta_path = os.path.splitext(image_path)[0] + ".json"
    with open(meta_path, "w") as f:
        json.dump(data, f, indent=4)

def shift_stats():
    stats = {
        "A": {"Defect Confirmed": 0, "False Alarm": 0},
        "B": {"Defect Confirmed": 0, "False Alarm": 0},
        "C": {"Defect Confirmed": 0, "False Alarm": 0}
    }

    for t in TUNNELS.values():
        for f in os.listdir(t["image_dir"]):
            if f.endswith(".json"):
                with open(os.path.join(t["image_dir"], f)) as j:
                    d = json.load(j)
                    sh = d.get("shift")
                    res = d.get("operator_decision")
                    if sh in stats and res in stats[sh]:
                        stats[sh][res] += 1
    return stats

# ===================== SIDEBAR =====================
st.sidebar.title("Operator Details")
op_name = st.sidebar.text_input("Operator Name")
op_id = st.sidebar.text_input("Operator ID")
shift = st.sidebar.selectbox("Shift", ["A", "B", "C"])

# ===================== CAMERA CONTROL =====================
st.sidebar.divider()
st.sidebar.subheader("📷 Camera Control")

if st.sidebar.button("🔴 LIVE + TRIGGER"):
    st.session_state["live"] = True
    trigger_shutter()

if st.sidebar.button("⏹ STOP LIVE"):
    st.session_state["live"] = False

# ===================== LIVE CAMERA =====================
if st.session_state.get("live", False):
    st.subheader("🔴 Live Camera Feed")

    frame_window = st.empty()
    cap = cv2.VideoCapture(0)

    while st.session_state.get("live", False):
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_window.image(frame)

    cap.release()

# ===================== HEADER =====================
st.title("Special Bar Mill – Defect Validation Dashboard")
st.divider()

# ===================== MAIN VIEW =====================
c1, c2 = st.columns(2)

for col, (tunnel, cfg) in zip([c1, c2], TUNNELS.items()):
    refresh_key = f"refresh_{tunnel}"
    img = get_latest_image(cfg["image_dir"], st.session_state.get(refresh_key, True))

    with col:
        st.subheader(tunnel)

        if img:
            annots = get_all_annotations(cfg["annot_dir"], img)
            meta: Dict[str, Any] = load_meta(img)

            i1, i2 = st.columns(2)

            with i1:
                st.image(Image.open(img), width=IMAGE_W)

            with i2:
                if annots:
                    for a in annots:
                        st.image(Image.open(a), width=ANNOT_W)
                else:
                    st.info("No annotations")

            decision = st.radio(
                "Final decision:",
                ["Not Validated", "Defect Confirmed", "False Alarm"],
                key=f"dec_{tunnel}"
            )

            if st.button(f"Save Validation – {tunnel}"):
                if not op_name or not op_id:
                    st.error("Operator details required")
                elif decision == "Not Validated":
                    st.error("Select decision")
                else:
                    meta.update({
                        "operator_name": op_name,
                        "operator_id": op_id,
                        "shift": shift,
                        "operator_decision": decision,
                        "validated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })

                    save_meta(img, meta)
                    st.success("Saved")
                    st.rerun()

        else:
            st.warning("No image available")

# ===================== STATS =====================
st.divider()
st.subheader("📊 Shift-wise Statistics")

stats = shift_stats()
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
st.caption("SBM Inline Vision System | Human-in-Loop Validation")
