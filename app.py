"""SoulMatch by RedPrana — Streamlit entry point."""

import streamlit as st

from soulmatch import auth, billing, landing, legal, theme
from soulmatch.db import get_session, init_db
from soulmatch.errors import init_error_reporting


@st.dialog("Privacy Policy")
def _show_privacy_dialog() -> None:
    st.markdown(legal.PRIVACY_POLICY_MD)


@st.dialog("Terms of Service")
def _show_terms_dialog() -> None:
    st.markdown(legal.TERMS_MD)

init_error_reporting()

# White lockup: the authenticated sidebar is deep maroon (see theme.py), and
# the landing page hides the logo entirely, so the white version is safe app-wide.
LOGO_PATH = "assets/logo-white.svg"
MARK_PATH = "assets/mark.svg"

st.set_page_config(page_title="SoulMatch by RedPrana", page_icon=MARK_PATH, layout="wide")
st.logo(LOGO_PATH, size="large")

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
                    "plan": restored.plan,
                }
            else:
                del st.query_params["token"]

if auth.current_user() is None:
    # Pre-login landing page (soulmatch/landing.py). The login card is a real
    # st.container(key=...) — Streamlit tags it with a stable CSS class
    # (st-key-login_card) that the landing CSS styles into a floating card.
    landing.inject_css()
    st.markdown('<div id="ai-soulmatch-top"></div>', unsafe_allow_html=True)

    hero_left, hero_right = st.columns([1.35, 1], gap="large")
    with hero_left:
        landing.render_hero_left()
    with hero_right:
        with st.container(key="login_card"):
            st.markdown(
                '<img src="/app/static/mark.svg" style="height:40px; margin-bottom:6px;"/>'
                '<div style="font:500 0.8rem/1 Inter,sans-serif; color:#7A6E66; margin-bottom:14px;">'
                'SoulMatch by RedPrana</div>',
                unsafe_allow_html=True,
            )
            tab_signin, tab_signup = st.tabs(["Sign in", "Create account"])
            with tab_signin:
                st.caption("Sign in to continue to your private workspace.")
                with st.form("login"):
                    username = st.text_input("Email or username")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
                if submitted:
                    locked = False
                    with get_session() as session:
                        if auth.is_locked_out(session, username):
                            locked = True
                        else:
                            user = auth.authenticate(session, username, password)
                            if user:
                                st.session_state["user"] = {
                                    "id": user.id, "username": user.username,
                                    "full_name": user.full_name, "role": user.role,
                                    "plan": user.plan,
                                }
                                st.query_params["token"] = auth.mint_session_token(user)
                    if auth.current_user():
                        st.rerun()
                    elif locked:
                        st.error(auth.LOCKOUT_MESSAGE)
                    else:
                        st.error("Invalid username or password.")
            with tab_signup:
                st.caption("Free to start — your data stays private to your account.")
                with st.form("signup"):
                    su_name = st.text_input("Your name")
                    su_email = st.text_input("Email")
                    su_password = st.text_input("Password", type="password")
                    su_password2 = st.text_input("Confirm password", type="password")
                    su_agree = st.checkbox("I agree to the Terms & Privacy Policy")
                    su_submitted = st.form_submit_button(
                        "Create free account", type="primary", use_container_width=True
                    )
                dc1, dc2 = st.columns(2)
                if dc1.button("Privacy Policy", key="show_privacy", use_container_width=True):
                    _show_privacy_dialog()
                if dc2.button("Terms", key="show_terms", use_container_width=True):
                    _show_terms_dialog()
                if su_submitted:
                    # Simple per-connection rate limit against scripted signup abuse.
                    attempts = st.session_state.get("_signup_attempts", 0) + 1
                    st.session_state["_signup_attempts"] = attempts
                    if attempts > 5:
                        st.error("Too many attempts — please refresh the page and try again later.")
                    elif su_password != su_password2:
                        st.error("Passwords do not match.")
                    elif not su_agree:
                        st.error("Please agree to the Terms & Privacy Policy to continue.")
                    else:
                        try:
                            with get_session() as session:
                                new_user = auth.register_member(session, su_email, su_password, su_name)
                                st.session_state["user"] = {
                                    "id": new_user.id, "username": new_user.username,
                                    "full_name": new_user.full_name, "role": new_user.role,
                                    "plan": new_user.plan,
                                }
                                st.query_params["token"] = auth.mint_session_token(new_user)
                        except ValueError as e:
                            st.error(str(e))
                        if auth.current_user():
                            st.rerun()

    landing.render_sections()
    st.stop()

current = auth.current_user()

# V3-3-4: refresh plan/lifecycle state from the DB on every page load — a
# webhook (payment failure, cancellation, ...) can change it mid-session,
# and there's no cron to push that into session_state some other way.
with get_session() as _session:
    _user_row = _session.get(auth.User, current["id"])
    billing.sync_plan_status(_session, _user_row)
    current["plan"] = billing.effective_plan(_user_row)
    current["actual_plan"] = _user_row.plan
    current["plan_status"] = _user_row.plan_status
    current["plan_grace_until"] = _user_row.plan_grace_until
    st.session_state["user"] = current

theme.apply()  # brand CSS for every authenticated page (pages run below via nav.run())

if current["plan_status"] == "past_due" and current["plan_grace_until"]:
    st.warning(
        f"⚠️ Your last payment didn't go through — you still have full access until "
        f"{current['plan_grace_until']:%d %b %Y}. Update your payment method on **My Plan**."
    )
elif current["plan_status"] == "paused":
    st.info("Your subscription is paused — you're on the Free plan for now. Resume anytime on **My Plan**.")

with st.sidebar:
    display_name = current["full_name"] or current["username"]
    initials = "".join(w[0] for w in display_name.split()[:2]).upper() or "?"
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px; padding:10px 4px 4px 4px;">
          <div style="width:40px; height:40px; border-radius:50%; flex:0 0 auto;
                      background:linear-gradient(135deg,#E8C55B,#C9A227); color:#4A1226;
                      font:700 0.95rem/40px Inter,sans-serif; text-align:center;">{initials}</div>
          <div>
            <div style="font:700 0.95rem/1.3 Inter,sans-serif; color:#FFF3E4;">{display_name}</div>
            <div style="font:500 0.75rem/1.3 Inter,sans-serif; color:rgba(255,243,228,0.65);
                        text-transform:uppercase; letter-spacing:0.06em;">{current["role"]}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
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
                    else:
                        try:
                            auth.change_password(session, user, new_pw)
                        except ValueError as e:
                            st.error(str(e))
                        else:
                            # re-mint immediately so the current session (which still
                            # has the old token in the URL) isn't logged out too
                            st.query_params["token"] = auth.mint_session_token(user)
                            st.success("Password updated.")

dashboard = st.Page("pages_/1_Dashboard.py", title="Dashboard", icon=":material/space_dashboard:", default=True)
ingest = st.Page("pages_/2_Ingest.py", title="Import Profiles", icon=":material/upload_file:")
profiles = st.Page("pages_/3_Profiles.py", title="Profiles", icon=":material/contacts:")
matching = st.Page("pages_/4_Matching.py", title="Matchmaking", icon=":material/favorite:")
astro = st.Page("pages_/5_Astrology.py", title="Horoscope Check", icon=":material/nights_stay:")
tasks = st.Page("pages_/6_Tasks.py", title="Tasks", icon=":material/task_alt:")
search = st.Page("pages_/8_Search.py", title="Search & Insights", icon=":material/manage_search:")
my_plan = st.Page("pages_/9_My_Plan.py", title="My Plan", icon=":material/workspace_premium:")

pages = [dashboard, ingest, profiles, matching, astro, tasks, search, my_plan]
if auth.is_admin(current["role"]):
    pages.append(st.Page("pages_/7_Users.py", title="Customers", icon=":material/group:"))

nav = st.navigation(pages)
nav.run()
