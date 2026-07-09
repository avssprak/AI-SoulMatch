"""AI-SoulMatch — Streamlit entry point."""

import streamlit as st

from soulmatch import auth
from soulmatch.db import get_session, init_db

st.set_page_config(page_title="AI-SoulMatch", page_icon="💞", layout="wide")

init_db()
with get_session() as _session:
    auth.ensure_bootstrap_admin(_session)

if auth.current_user() is None:
    st.title("💞 AI-SoulMatch")
    st.caption("Sign in to continue.")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        with get_session() as session:
            user = auth.authenticate(session, username, password)
            if user:
                st.session_state["user"] = {
                    "id": user.id, "username": user.username,
                    "full_name": user.full_name, "role": user.role,
                }
        if auth.current_user():
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()

current = auth.current_user()

with st.sidebar:
    st.markdown(f"**{current['full_name'] or current['username']}**")
    st.caption(current["role"])
    if st.button("Log out"):
        del st.session_state["user"]
        st.rerun()
    with st.expander("Change password"):
        with st.form("change_password", clear_on_submit=True):
            old_pw = st.text_input("Current password", type="password")
            new_pw = st.text_input("New password", type="password")
            if st.form_submit_button("Update password"):
                with get_session() as session:
                    user = session.get(auth.User, current["id"])
                    if not auth.verify_password(old_pw, user.password_hash):
                        st.error("Current password is incorrect.")
                    elif len(new_pw) < 6:
                        st.error("New password must be at least 6 characters.")
                    else:
                        auth.change_password(session, user, new_pw)
                        st.success("Password updated.")

dashboard = st.Page("pages_/1_Dashboard.py", title="Dashboard", icon="📊", default=True)
ingest = st.Page("pages_/2_Ingest.py", title="Ingest WhatsApp", icon="📥")
profiles = st.Page("pages_/3_Profiles.py", title="Profiles", icon="🗂️")
matching = st.Page("pages_/4_Matching.py", title="Matching", icon="💘")
astro = st.Page("pages_/5_Astrology.py", title="Astrology", icon="🔯")
tasks = st.Page("pages_/6_Tasks.py", title="Tasks", icon="✅")

pages = [dashboard, ingest, profiles, matching, astro, tasks]
if auth.is_admin(current["role"]):
    pages.append(st.Page("pages_/7_Users.py", title="Users", icon="👤"))

nav = st.navigation(pages)
nav.run()
