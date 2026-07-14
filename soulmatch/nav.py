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

# Centralized page paths — every st.switch_page / st.Page target should use
# one of these instead of a literal string, so a future rename (V4-1) is a
# one-line change instead of a grep-and-replace across pages_/*.py.
WELCOME_PAGE = "pages_/00_Welcome.py"
MY_CHILD_PAGE = "pages_/0_My_Child.py"
DASHBOARD_PAGE = "pages_/1_Dashboard.py"
INGEST_PAGE = "pages_/2_Ingest.py"
PROFILES_PAGE = "pages_/3_Profiles.py"
MATCHING_PAGE = "pages_/4_Matching.py"
TASKS_PAGE = "pages_/6_Tasks.py"
USERS_PAGE = "pages_/7_Users.py"
SEARCH_PAGE = "pages_/8_Search.py"
MY_PLAN_PAGE = "pages_/9_My_Plan.py"
GUIDE_PAGE = "pages_/10_Guide.py"


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


def next_step_button(label: str, target: str, *, key: str, profile_id: int | None = None) -> None:
    """Render the single primary "what next" action after a page's main task
    succeeds (V4-1-3) — e.g. after saving a candidate, "Score against
    <child> ->". If `profile_id` is given, it's queued the same way
    `open_profile_button` queues one, so the target page opens straight to it."""
    if st.button(label, key=key, type="primary"):
        if profile_id is not None:
            request_open_profile(profile_id)
        st.switch_page(target)


_NEXT_STEP_KEY = "_next_step"


def queue_next_step(label: str, target: str, *, profile_id: int | None = None) -> None:
    """Queue a next-step suggestion to render on the next run, after an
    st.rerun() — same reason as soulmatch.ui.flash(): a button rendered right
    before st.rerun() never reaches the user's eyes. Call this right where a
    page's main action succeeds (import processed, candidate saved, match
    saved); render it with show_next_step() near the top of the page,
    alongside show_flash()."""
    st.session_state[_NEXT_STEP_KEY] = (label, target, profile_id)


def show_next_step() -> None:
    """Render and clear a queued next-step suggestion, if any. Call once near
    the top of a page, after show_flash()."""
    queued = st.session_state.pop(_NEXT_STEP_KEY, None)
    if queued is None:
        return
    label, target, profile_id = queued
    next_step_button(label, target, key="_next_step_btn", profile_id=profile_id)
