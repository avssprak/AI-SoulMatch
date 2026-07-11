"""Cross-page navigation helpers.

Streamlit pages are independent scripts; there's no built-in way to say
"open profile #8 on the Profiles page" from elsewhere. This module queues
the target in session_state (the same deferred-flag pattern
`_clear_profiles_selection` already uses in pages_/3_Profiles.py, since a
target page can't have its widgets pre-seeded before it has even run once)
and the caller follows up with st.switch_page().
"""

from __future__ import annotations

import streamlit as st

OPEN_PROFILE_KEY = "open_profile_id"
TASKS_OVERDUE_PREF_KEY = "tasks_overdue_pref"

PROFILES_PAGE = "pages_/3_Profiles.py"
TASKS_PAGE = "pages_/6_Tasks.py"
SEARCH_PAGE = "pages_/8_Search.py"


def request_open_profile(profile_id: int) -> None:
    """Queue `profile_id` to be selected next time the Profiles page renders."""
    st.session_state[OPEN_PROFILE_KEY] = profile_id


def consume_open_profile_request() -> int | None:
    """Pop and return a queued profile id, if any. Call once, at the very top
    of pages_/3_Profiles.py, before any widget with a stateful key exists."""
    return st.session_state.pop(OPEN_PROFILE_KEY, None)


def open_profile_button(profile_id: int, label: str = "Open profile", key: str | None = None) -> None:
    """Render a button that navigates straight to a profile's detail view."""
    if st.button(label, key=key or f"open_profile_btn_{profile_id}"):
        request_open_profile(profile_id)
        st.switch_page(PROFILES_PAGE)
