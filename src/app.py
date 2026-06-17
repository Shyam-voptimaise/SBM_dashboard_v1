from __future__ import annotations

import streamlit as st

from image_store import latest_data_signature
from runtime_config import APP_FOOTER, APP_TITLE, PAGE_TITLE, REFRESH_INTERVAL, TUNNELS
from ui.main_page import render_main_page
from ui.sidebar import render_sidebar

DATA_SIGNATURE_KEY = "sbm_latest_data_signature"


def _watch_interval() -> str | None:
    if REFRESH_INTERVAL <= 0:
        return None
    return f"{REFRESH_INTERVAL}s"


@st.fragment(run_every=_watch_interval())
def watch_for_new_data() -> None:
    if REFRESH_INTERVAL <= 0:
        return

    signature = latest_data_signature(TUNNELS)
    previous_signature = st.session_state.get(DATA_SIGNATURE_KEY)
    st.session_state[DATA_SIGNATURE_KEY] = signature

    if previous_signature is not None and signature != previous_signature:
        st.rerun()


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    watch_for_new_data()
    sidebar_state = render_sidebar()

    st.title(APP_TITLE)
    st.divider()
    render_main_page(sidebar_state)

    st.divider()
    st.caption(APP_FOOTER)


if __name__ == "__main__":
    main()
