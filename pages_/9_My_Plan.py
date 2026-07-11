"""Module 15 — My Plan (V3-2-4): plan status, AI-action usage, and the
plan-comparison table. Payments (upgrade/downgrade) arrive in Sprint V3-3 —
until then the upgrade buttons are informational placeholders.
"""

import streamlit as st

from soulmatch import auth, billing, theme
from soulmatch.db import get_session
from soulmatch.tenancy import owner_id_of

current_user = auth.require_login()
owner = owner_id_of(current_user)
plan = current_user.get("plan", "free")

theme.page_header("My Plan", "Your subscription, AI-action usage, and what each plan includes.")

with get_session() as session:
    status = billing.quota_status(session, current_user)

c1, c2 = st.columns([1, 2])
with c1:
    st.metric("Current plan", plan.capitalize())
with c2:
    limit_text = "Unlimited" if status.limit is None else str(status.limit)
    st.markdown(f"**AI actions used this month:** {status.used} / {limit_text}")
    if status.limit is not None:
        st.progress(min(status.used / status.limit, 1.0) if status.limit else 0.0)
    st.caption(f"Resets on {status.resets_on:%d %b %Y}.")
    if status.exhausted:
        st.warning(
            f"You've used all {status.limit} AI actions this month — upgrade below or wait "
            f"until {status.resets_on:%d %b} for the reset."
        )

st.divider()
theme.section("Plans", "Prices shown in INR — see billing.PRICE_CATALOG for USD/NRI pricing (arrives in V3-3).")

plan_cols = st.columns(3)
plan_details = [
    ("free", "Free", billing.PLAN_PRICES_INR["free"]),
    ("plus", "Plus", billing.PLAN_PRICES_INR["plus"]),
    ("pro", "Pro", billing.PLAN_PRICES_INR["pro"]),
]
for col, (plan_key, label, price) in zip(plan_cols, plan_details):
    limits = billing.limits_for(plan_key)
    with col:
        with st.container(border=True):
            is_current = plan_key == plan
            st.markdown(f"### {label}" + (" ✅ current" if is_current else ""))
            st.markdown(f"**₹{price}/mo**" if price else "**Free**")
            st.markdown(f"- {limits['ai_actions']} AI actions/mo")
            st.markdown(
                "- " + ("Unlimited profiles" if limits["profiles"] is None else f"{limits['profiles']} profiles")
            )
            st.markdown(f"- {limits['children']} child/children")
            st.markdown("- " + ("✅" if limits["ai_explanations"] else "❌") + " AI match explanations")
            st.markdown("- " + ("✅" if limits["nl_search"] else "❌") + " Natural-language search")
            bulk = limits["bulk_imports"]
            st.markdown(
                "- " + ("Unlimited bulk imports" if bulk is None else f"{bulk} bulk import(s)/mo" if bulk else "No bulk import")
            )
            if not is_current:
                st.button(
                    f"Upgrade to {label}" if price else f"Downgrade to {label}",
                    key=f"upgrade_{plan_key}", disabled=True,
                    help="Payments arrive in Sprint V3-3 — talk to support@redprana.com for now.",
                )
