from datetime import date

import streamlit as st

from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, chart_summary
from soulmatch.astrology.geo import lookup as geo_lookup

st.title("🔯 Astrology Explorer")
st.caption("Standalone chart lookup (Lahiri sidereal) — useful for verifying a horoscope without a full match.")

col1, col2, col3 = st.columns(3)
dob = col1.date_input("Date of Birth", value=date(1995, 1, 1), min_value=date(1930, 1, 1), max_value=date.today())
birth_time = col2.text_input("Birth Time (24h HH:MM)", value="10:30")
birth_place = col3.text_input("Birth Place", value="Bangalore")

if st.button("Compute Chart", type="primary"):
    place = geo_lookup(birth_place)
    if place is None:
        st.error(f"Could not find '{birth_place}' in the offline place database. Try a larger nearby city.")
    else:
        st.caption(f"Resolved to {place.name}, {place.country} ({place.latitude:.3f}, {place.longitude:.3f}), "
                   f"timezone {place.timezone}")
        try:
            chart = build_chart(BirthDetails(dob, birth_time, birth_place))
        except AstrologyError as e:
            st.error(str(e))
        else:
            summary = chart_summary(chart)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Nakshatra", summary["nakshatra"])
            c2.metric("Pada", summary["pada"])
            c3.metric("Rashi (Moon Sign)", summary["rashi"])
            c4.metric("Lagna (Ascendant)", summary["lagna"])

            st.subheader("Planetary Positions (Sidereal)")
            from soulmatch.astrology.ephemeris import RASHIS

            rows = []
            for planet, lon in chart.planet_longitudes.items():
                sign = int(lon // 30)
                deg_in_sign = lon % 30
                rows.append({"Planet": planet, "Sign": RASHIS[sign], "Degree": f"{deg_in_sign:.2f}°"})
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

st.divider()
st.caption(
    "Note: this engine uses Swiss Ephemeris's built-in Moshier model (no external ephemeris files) "
    "with Lahiri ayanamsa — accurate for nakshatra/rashi/lagna determination used in Ashta Koota matching."
)
