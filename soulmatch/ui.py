"""Tiny UI helpers shared across pages_/*.py.

Streamlit reruns the whole script on every interaction. A st.success(...)
immediately followed by st.rerun() never reaches the user's eyes — the
rerun redraws the page before the message paints. flash()/show_flash() queue
a message in session_state so it survives exactly one rerun.
"""

from __future__ import annotations

import streamlit as st

_KEY = "_flash"
_RENDERERS = {
    "success": st.success,
    "warning": st.warning,
    "error": st.error,
    "info": st.info,
}


def flash(message: str, kind: str = "success") -> None:
    """Queue a message to render on the next run, after an st.rerun()."""
    st.session_state.setdefault(_KEY, []).append((kind, message))


def show_flash() -> None:
    """Render and clear any queued flash messages. Call once near the top of each page."""
    messages = st.session_state.pop(_KEY, [])
    for kind, message in messages:
        _RENDERERS.get(kind, st.info)(message)
