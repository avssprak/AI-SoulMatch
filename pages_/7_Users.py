import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth, theme
from soulmatch.db import get_session
from soulmatch.models import ROLES, User
from soulmatch.ui import flash, show_flash

current_user = auth.require_admin()

theme.page_header(
    "User Management",
    "Administrator only. Roles: Administrator (full access + user management), "
    "Volunteer / Coordinator (create/edit everything), Viewer (read-only).",
)
show_flash()

with get_session() as session:
    users = session.scalars(select(User).order_by(User.username)).all()

rows = [{
    "ID": u.id, "Username": u.username, "Full Name": u.full_name or "—", "Role": u.role,
    "Active": "Yes" if u.is_active else "No",
    "Last Login": u.last_login.strftime("%d %b %Y %H:%M") if u.last_login else "Never",
} for u in users]
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

st.divider()
theme.section("Create User")
with st.form("create_user", clear_on_submit=True):
    c1, c2 = st.columns(2)
    new_username = c1.text_input("Username*")
    new_full_name = c2.text_input("Full Name")
    c1, c2, c3 = st.columns(3)
    new_password = c1.text_input("Password*", type="password")
    confirm_password = c2.text_input("Confirm Password*", type="password")
    new_role = c3.selectbox("Role", ROLES, index=ROLES.index("Volunteer"))
    if st.form_submit_button("Create user", type="primary"):
        if not new_username or not new_password:
            st.error("Username and password are required.")
        elif new_password != confirm_password:
            st.error("Passwords do not match.")
        elif len(new_password) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            with get_session() as session:
                existing = session.scalar(select(User).where(User.username == new_username.strip().lower()))
                if existing:
                    st.error(f"Username '{new_username}' is already taken.")
                else:
                    auth.create_user(session, new_username, new_password, new_full_name, new_role)
                    session.commit()
                    flash(f"User '{new_username}' created.")
                    st.rerun()

st.divider()
theme.section("Manage User")
if users:
    selected_id = st.selectbox(
        "Select user", [u.id for u in users],
        format_func=lambda uid: next(f"{u.username} ({u.role})" for u in users if u.id == uid),
    )
    with get_session() as session:
        target = session.get(User, selected_id)

        col1, col2, col3 = st.columns(3)
        with col1:
            new_role_choice = st.selectbox(
                "Role", ROLES, index=ROLES.index(target.role), key=f"role_{target.id}"
            )
            if new_role_choice != target.role and st.button("Update role"):
                target.role = new_role_choice
                session.commit()
                flash("Role updated.")
                st.rerun()
        with col2:
            if target.id == current_user["id"]:
                st.caption("You cannot deactivate your own account.")
            elif target.is_active:
                if st.button("Deactivate"):
                    target.is_active = False
                    session.commit()
                    flash(f"'{target.username}' deactivated.")
                    st.rerun()
            else:
                if st.button("Reactivate"):
                    target.is_active = True
                    session.commit()
                    flash(f"'{target.username}' reactivated.")
                    st.rerun()
        with col3:
            with st.popover("Reset password"):
                reset_pw = st.text_input("New password", type="password", key=f"reset_{target.id}")
                if st.button("Set password", key=f"reset_btn_{target.id}"):
                    if len(reset_pw) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        auth.change_password(session, target, reset_pw)
                        st.success("Password reset.")
else:
    st.info("No users yet.")
