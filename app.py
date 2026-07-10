"""AI-SoulMatch — Streamlit entry point."""

import streamlit as st

from soulmatch import auth
from soulmatch.db import get_session, init_db

st.set_page_config(page_title="AI-SoulMatch", page_icon="💞", layout="wide")

init_db()
with get_session() as _session:
    auth.ensure_bootstrap_admin(_session)

if auth.current_user() is None:
    # Restore login from a signed token in the URL (survives a browser refresh —
    # st.session_state alone doesn't, since it's tied to the WebSocket connection).
    token = st.query_params.get("token")
    if token:
        with get_session() as _session:
            restored = auth.validate_session_token(_session, token)
            if restored is not None:
                st.session_state["user"] = {
                    "id": restored.id, "username": restored.username,
                    "full_name": restored.full_name, "role": restored.role,
                }
            else:
                del st.query_params["token"]

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
                st.query_params["token"] = auth.mint_session_token(user)
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
        with get_session() as session:
            user = session.get(auth.User, current["id"])
            auth.logout_everywhere(session, user)
        del st.session_state["user"]
        if "token" in st.query_params:
            del st.query_params["token"]
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
                        # re-mint immediately so the current session (which still
                        # has the old token in the URL) isn't logged out too
                        st.query_params["token"] = auth.mint_session_token(user)
                        st.success("Password updated.")

dashboard = st.Page("pages_/1_Dashboard.py", title="Dashboard", icon="📊", default=True)
ingest = st.Page("pages_/2_Ingest.py", title="Import Messages", icon="📥")
profiles = st.Page("pages_/3_Profiles.py", title="Profiles", icon="🗂️")
matching = st.Page("pages_/4_Matching.py", title="Matching", icon="💘")
astro = st.Page("pages_/5_Astrology.py", title="Astrology", icon="🔯")
tasks = st.Page("pages_/6_Tasks.py", title="Tasks", icon="✅")
search = st.Page("pages_/8_Search.py", title="Search & Insights", icon="🔍")

pages = [dashboard, ingest, profiles, matching, astro, tasks, search]
if auth.is_admin(current["role"]):
    pages.append(st.Page("pages_/7_Users.py", title="Users", icon="👤"))

nav = st.navigation(pages)
nav.run()
