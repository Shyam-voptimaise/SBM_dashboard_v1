from __future__ import annotations

import streamlit as st

from sbm_dashboard.config import APP_TITLE, PAGE_TITLE, REFRESH_INTERVAL
from sbm_dashboard.ui.components import render_auto_refresh
from sbm_dashboard.ui.main_page import render_main_page
from sbm_dashboard.ui.sidebar import render_sidebar


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    render_auto_refresh(REFRESH_INTERVAL)

    sidebar_state = render_sidebar()

    st.title(APP_TITLE)
    st.divider()
    render_main_page(sidebar_state)

    st.divider()
    st.caption("SBM Inline Vision System | 2 Tunnel x 4 View Dashboard")


if __name__ == "__main__":
    main()
