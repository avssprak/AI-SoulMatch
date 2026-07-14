"""V5-2-1 — "How It Works": one expander per journey step, written for a
parent rather than an operator. Content lives in soulmatch/guide_content.py
so it's testable and has one place to translate later.

Reached either from the sidebar ("More" section) or via theme.help_link(),
which sets session_state["guide_anchor"] before switching here so the
relevant section opens already expanded (V5-2-2).
"""

import streamlit as st

from soulmatch import auth, theme
from soulmatch.guide_content import SECTION_ORDER, SECTIONS

auth.require_login()

theme.page_header("How It Works", "A quick reference for every step of the journey.")

anchor = st.session_state.pop("guide_anchor", None)

for key in SECTION_ORDER:
    title, body = SECTIONS[key]
    with st.expander(title, expanded=(key == anchor)):
        st.markdown(body)
