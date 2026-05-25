import streamlit as st
import os
import json
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

REFRESH_INTERVAL = 5  # seconds

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

# ===================== HEADER =====================
st.title("SBM – Multi Tunnel Defect Dashboard")
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
