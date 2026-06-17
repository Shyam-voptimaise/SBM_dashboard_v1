from __future__ import annotations

import streamlit as st

from runtime_config import APP_FOOTER, APP_TITLE, PAGE_TITLE, REFRESH_INTERVAL
from ui.main_page import render_main_page
from ui.sidebar import SidebarState, render_sidebar


def _refresh_interval() -> str:
    return f"{max(1, REFRESH_INTERVAL)}s"


@st.fragment(run_every=_refresh_interval())
def render_live_dashboard(sidebar_state: SidebarState) -> None:
    st.title(APP_TITLE)
    st.divider()
    render_main_page(sidebar_state)


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    sidebar_state = render_sidebar()
    render_live_dashboard(sidebar_state)

    st.divider()
    st.caption(APP_FOOTER)


if __name__ == "__main__":
    main()
