"""Tiny UI helpers shared across pages_/*.py.

Streamlit reruns the whole script on every interaction. A st.success(...)
immediately followed by st.rerun() never reaches the user's eyes — the
rerun redraws the page before the message paints. flash()/show_flash() queue
a message in session_state so it survives exactly one rerun.
"""

from __future__ import annotations

import streamlit as st

from .models import stage_group_label

# V3-5-3: server-side upload size cap. Streamlit's own `server.maxUploadSize`
# (.streamlit/config.toml) rejects anything bigger before the app even sees
# it; this is the smaller, app-level limit for the file types this app
# actually expects (biodata PDFs, photos) — deliberately much less than
# Streamlit's own ceiling.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def check_upload_size(uploaded_file) -> bool:
    """True if `uploaded_file` (an st.file_uploader result) is within
    MAX_UPLOAD_BYTES; shows a warning and returns False otherwise. Callers
    should skip processing the file when this returns False."""
    if uploaded_file is not None and uploaded_file.size > MAX_UPLOAD_BYTES:
        st.warning(
            f"'{uploaded_file.name}' is {uploaded_file.size / 1_048_576:.1f} MB — "
            f"the limit is {MAX_UPLOAD_BYTES / 1_048_576:.0f} MB. Choose a smaller file."
        )
        return False
    return True


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


# One color per stage *group* (see models.PIPELINE_STAGE_GROUPS), not one per
# individual stage — 15 distinct colors would be noise, not signal.
_GROUP_COLORS = {
    "Screening": "blue",
    "Outreach": "violet",
    "Outcome": "green",
}
_OUTCOME_COLORS = {"Marriage": "green", "Rejected": "red", "Closed": "gray", "Engagement": "green"}


def stage_badge(stage: str) -> str:
    """Markdown color-badge text for a pipeline stage, grouped by
    PIPELINE_STAGE_GROUPS. Render with st.markdown(stage_badge(stage))."""
    label = stage_group_label(stage)
    group = label.split(" — ")[0] if " — " in label else None
    color = _OUTCOME_COLORS.get(stage) or _GROUP_COLORS.get(group, "gray")
    return f":{color}-badge[{stage}]"
