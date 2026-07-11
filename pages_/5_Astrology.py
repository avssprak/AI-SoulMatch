from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, theme
from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, chart_summary
from soulmatch.astrology.ephemeris import RASHIS
from soulmatch.astrology.geo import lookup as geo_lookup
from soulmatch.db import get_session
from soulmatch.models import Activity, Profile
from soulmatch.tenancy import get_owned, owned, owner_id_of
from soulmatch.ui import flash, show_flash

current_user = auth.require_login()
owner = owner_id_of(current_user)
theme.page_header("Horoscope Check", "Standalone chart lookup (Lahiri sidereal) — verify a horoscope without running a full match.")
show_flash()

with get_session() as session:
    profiles = session.scalars(owned(select(Profile), Profile, owner).order_by(Profile.full_name)).all()

MANUAL_ENTRY = "— Manual entry —"
selected = st.selectbox(
    "Load birth details from an existing Bride/Groom profile (optional)",
    [MANUAL_ENTRY] + [p.id for p in profiles],
    format_func=lambda pid: pid if pid == MANUAL_ENTRY else next(
        f"#{p.id} {p.full_name or 'Unnamed'} ({p.gender or '?'})" for p in profiles if p.id == pid
    ),
)

selected_profile = None if selected == MANUAL_ENTRY else next(p for p in profiles if p.id == selected)
if selected_profile and not (selected_profile.dob and selected_profile.birth_time and selected_profile.birth_place):
    st.warning("This profile is missing some birth details — fill in the gaps below manually.")

col1, col2, col3 = st.columns(3)
widget_key = str(selected)
dob = col1.date_input(
    "Date of Birth",
    value=(selected_profile.dob if selected_profile and selected_profile.dob else date(1995, 1, 1)),
    min_value=date(1930, 1, 1), max_value=date.today(), key=f"astro_dob_{widget_key}",
)
birth_time = col2.text_input(
    "Birth Time (24h HH:MM)",
    value=(selected_profile.birth_time if selected_profile and selected_profile.birth_time else "10:30"),
    key=f"astro_time_{widget_key}",
)
birth_place = col3.text_input(
    "Birth Place",
    value=(selected_profile.birth_place if selected_profile and selected_profile.birth_place else "Bangalore"),
    key=f"astro_place_{widget_key}",
)

if st.button("Compute Chart", type="primary"):
    place = geo_lookup(birth_place)
    if place is None:
        st.error(f"Could not find '{birth_place}' in the offline place database. Try a larger nearby city.")
    else:
        try:
            chart = build_chart(BirthDetails(dob, birth_time, birth_place))
        except AstrologyError as e:
            st.error(str(e))
        else:
            st.session_state["astro_chart"] = {
                "profile_id": selected_profile.id if selected_profile else None,
                "dob": dob, "birth_time": birth_time, "birth_place": birth_place,
                "place_resolved": (
                    f"{place.name}, {place.country} ({place.latitude:.3f}, {place.longitude:.3f}), "
                    f"timezone {place.timezone}"
                ),
                "summary": chart_summary(chart),
                "planet_longitudes": dict(chart.planet_longitudes),
            }
    st.rerun()

chart_state = st.session_state.get("astro_chart")
if chart_state and chart_state["dob"] == dob and chart_state["birth_time"] == birth_time \
        and chart_state["birth_place"] == birth_place:
    st.caption(f"Resolved to {chart_state['place_resolved']}")
    summary = chart_state["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nakshatra", summary["nakshatra"], summary["nakshatra_te"], delta_color="off")
    c2.metric("Pada", summary["pada"])
    c3.metric("Rashi (Moon Sign)", summary["rashi"], summary["rashi_te"], delta_color="off")
    c4.metric("Lagna (Ascendant)", summary["lagna"], summary["lagna_te"], delta_color="off")

    theme.section("Planetary Positions (Sidereal)")
    rows = []
    for planet, lon in chart_state["planet_longitudes"].items():
        sign = int(lon // 30)
        deg_in_sign = lon % 30
        rows.append({"Planet": planet, "Sign": RASHIS[sign], "Degree": f"{deg_in_sign:.2f}°"})
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    if chart_state["profile_id"] is not None:
        profile_id = chart_state["profile_id"]
        with get_session() as session:
            target_profile = get_owned(session, Profile, profile_id, owner)
        existing_fields = [f for f in ("nakshatra", "rashi", "lagna") if getattr(target_profile, f)]
        overwrite = False
        if existing_fields:
            overwrite = st.checkbox(
                f"Overwrite existing values ({', '.join(existing_fields)})", key=f"astro_overwrite_{profile_id}"
            )
        if st.button(f"Save to profile #{profile_id}", key=f"astro_save_{profile_id}", type="primary"):
            with get_session() as session:
                target_profile = get_owned(session, Profile, profile_id, owner)
                changed = []
                for field in ("nakshatra", "rashi", "lagna"):
                    value = summary[field]
                    if not getattr(target_profile, field) or overwrite:
                        if getattr(target_profile, field) != value:
                            setattr(target_profile, field, value)
                            changed.append(field)
                if not target_profile.horoscope_available:
                    target_profile.horoscope_available = True
                    changed.append("horoscope_available")
                session.add(Activity(
                    profile_id=target_profile.id, owner_user_id=owner, event="Astrology computed",
                    detail=f"Nakshatra {summary['nakshatra']}, Rashi {summary['rashi']}, Lagna {summary['lagna']}",
                    created_by_user_id=current_user["id"],
                ))
                session.commit()
            flash(
                f"Saved to profile #{profile_id}: {', '.join(changed)}."
                if changed else f"Profile #{profile_id} already up to date — no changes."
            )
            st.rerun()

st.divider()
st.caption(
    "Note: this engine uses Swiss Ephemeris's built-in Moshier model (no external ephemeris files) "
    "with Lahiri ayanamsa — accurate for nakshatra/rashi/lagna determination used in Ashta Koota matching."
)
