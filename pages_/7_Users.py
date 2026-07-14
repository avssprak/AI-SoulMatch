"""Admin-only operator surface (V3-1-5): customer list and account controls.

This page never touches another tenant's domain rows — only the users table
plus per-tenant row counts for support context.
"""

import pandas as pd
import streamlit as st
from sqlalchemy import func, select

from soulmatch import auth, billing, theme
from soulmatch.db import get_session
from soulmatch.models import PLANS, Profile, Subscription, User
from soulmatch.timezones import to_local
from soulmatch.ui import flash, show_flash

current_user = auth.require_admin()

theme.page_header(
    "Customers",
    "Platform operator view — every account, its plan, and account controls. "
    "Customer data itself stays private to each member.",
)
show_flash()

with get_session() as session:
    users = session.scalars(select(User).order_by(User.created_at.desc())).all()
    profile_counts = dict(
        session.execute(
            select(Profile.owner_user_id, func.count(Profile.id)).group_by(Profile.owner_user_id)
        ).all()
    )
    # Latest subscription row per owner — status is left to the gateway, but
    # interval/current_period_end are what the operator needs to answer
    # "monthly or annual, and when does it renew/expire" without leaving
    # this page (V3-3 Subscription rows are webhook-maintained).
    latest_subs: dict[int, Subscription] = {}
    for sub in session.scalars(select(Subscription).order_by(Subscription.updated_at.asc())).all():
        latest_subs[sub.owner_user_id] = sub

member_count = sum(1 for u in users if u.role == auth.MEMBER_ROLE)
c1, c2, c3 = st.columns(3)
c1.metric("Members", member_count)
c2.metric("On paid plans", sum(1 for u in users if u.plan in ("plus", "pro")))
c3.metric("Active accounts", sum(1 for u in users if u.is_active))

rows = []
for u in users:
    sub = latest_subs.get(u.id)
    billing_interval = sub.interval.capitalize() if sub and sub.interval else "—"
    period_end = (
        to_local(sub.current_period_end, current_user.get("timezone")).strftime("%d %b %Y")
        if sub and sub.current_period_end else "—"
    )
    rows.append({
        "ID": u.id, "Email / Username": u.email or u.username, "Name": u.full_name or "—",
        "Role": u.role, "Plan": u.plan, "Billing": billing_interval, "Renews / Expires": period_end,
        "Profiles": profile_counts.get(u.id, 0),
        "Active": "Yes" if u.is_active else "No",
        "Joined": to_local(u.created_at, current_user.get("timezone")).strftime("%d %b %Y") if u.created_at else "—",
        "Last Login": to_local(u.last_login, current_user.get("timezone")).strftime("%d %b %Y %H:%M") if u.last_login else "Never",
    })
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

st.divider()
theme.section("Manage account")
if users:
    selected_id = st.selectbox(
        "Select account", [u.id for u in users],
        format_func=lambda uid: next(f"{u.email or u.username} ({u.role}, {u.plan})" for u in users if u.id == uid),
    )
    with get_session() as session:
        target = session.get(User, selected_id)

        col1, col2, col3 = st.columns(3)
        with col1:
            # Manual plan override — support/comp tool until billing (V3-3)
            # sets this automatically via payment webhooks.
            new_plan = st.selectbox("Plan", PLANS, index=PLANS.index(target.plan), key=f"plan_{target.id}")
            if new_plan != target.plan and st.button("Update plan"):
                target.plan = new_plan
                session.commit()
                flash(f"'{target.username}' moved to {new_plan}.")
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
                    if len(reset_pw) < auth.MIN_PASSWORD_LENGTH:
                        st.error(f"Password must be at least {auth.MIN_PASSWORD_LENGTH} characters.")
                    else:
                        auth.change_password(session, target, reset_pw)
                        st.success("Password reset.")
else:
    st.info("No accounts yet.")

st.divider()
theme.section("AI usage this month", "Platform-wide, across every tenant.")
with get_session() as session:
    summary = billing.monthly_usage_summary(session)
u1, u2 = st.columns(2)
u1.metric("Estimated API cost", f"₹{summary['total_cost_inr']:.2f}")
with u2:
    st.markdown("**Actions by type**")
    if summary["by_action"]:
        st.dataframe(pd.DataFrame(
            [{"Action": k, "Count": v} for k, v in summary["by_action"].items()]
        ), width="stretch", hide_index=True)
    else:
        st.caption("No metered AI actions recorded yet this month.")
st.markdown("**Top 5 heaviest users (by estimated cost)**")
if summary["top_users"]:
    st.dataframe(pd.DataFrame(summary["top_users"]), width="stretch", hide_index=True)
else:
    st.caption("No usage yet.")
