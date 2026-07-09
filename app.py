"""AI-SoulMatch — Streamlit entry point."""

import streamlit as st

from soulmatch.db import init_db

st.set_page_config(page_title="AI-SoulMatch", page_icon="💞", layout="wide")

init_db()

dashboard = st.Page("pages_/1_Dashboard.py", title="Dashboard", icon="📊", default=True)
ingest = st.Page("pages_/2_Ingest.py", title="Ingest WhatsApp", icon="📥")
profiles = st.Page("pages_/3_Profiles.py", title="Profiles", icon="🗂️")
matching = st.Page("pages_/4_Matching.py", title="Matching", icon="💘")
astro = st.Page("pages_/5_Astrology.py", title="Astrology", icon="🔯")

nav = st.navigation([dashboard, ingest, profiles, matching, astro])
nav.run()
