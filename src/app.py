from __future__ import annotations

import streamlit as st

from runtime_config import APP_FOOTER, APP_TITLE, PAGE_TITLE
from ui.main_page import render_main_page
from ui.sidebar import render_sidebar


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    sidebar_state = render_sidebar()

    st.title(APP_TITLE)
    st.divider()
    render_main_page(sidebar_state)

    st.divider()
    st.caption(APP_FOOTER)


if __name__ == "__main__":
    main()
