"""V4-3-1 — shared "compute & save a horoscope" UI, folded out of the
standalone pages_/5_Astrology.py page into the profile drawer (Candidates)
and Match & Compare, so a member never has to leave what they're doing to
get a chart. One Session's worth of work (build the chart, write
nakshatra/rashi/lagna + horoscope_available, log an Activity) shared by
every caller instead of copy-pasted per page.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

from .astrology.engine import AstrologyError, BirthDetails, build_chart, chart_summary
from .astrology.geo import lookup as geo_lookup
from .models import Activity, Profile
from .profiles import is_match_ready
from .ui import flash


def compute_and_save_chart(
    session: Session, owner: int, current_user: dict, profile: Profile, *, key_prefix: str,
) -> None:
    """Render a "Compute & save chart" button for `profile` and, on click,
    build the chart and persist nakshatra/rashi/lagna + horoscope_available.
    Assumes the caller has already checked `is_match_ready(profile)` isn't
    required to render (missing birth details are reported inline)."""
    if not is_match_ready(profile):
        st.caption("Add date, time & place of birth first.")
        return

    if st.button("Compute & save chart", key=f"{key_prefix}_compute_chart_{profile.id}"):
        place = geo_lookup(profile.birth_place)
        if place is None:
            st.error(
                f"Could not find '{profile.birth_place}' in the offline place database. "
                "Try a larger nearby city."
            )
            return
        try:
            chart = build_chart(BirthDetails(profile.dob, profile.birth_time, profile.birth_place))
        except AstrologyError as e:
            st.error(str(e))
            return
        summary = chart_summary(chart)
        profile.nakshatra = summary["nakshatra"]
        profile.rashi = summary["rashi"]
        profile.lagna = summary["lagna"]
        profile.horoscope_available = True
        session.add(Activity(
            profile_id=profile.id, owner_user_id=owner, event="Astrology computed",
            detail=f"Nakshatra {summary['nakshatra']}, Rashi {summary['rashi']}, Lagna {summary['lagna']}",
            created_by_user_id=current_user["id"],
        ))
        session.commit()
        flash(f"Horoscope computed and saved for #{profile.id}.")
        st.rerun()
