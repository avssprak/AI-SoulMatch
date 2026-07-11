"""Module 15/16 — My Plan: plan status, AI-action usage, the plan-comparison
table (V3-2), and checkout/pause/resume (V3-3).

Checkout only works once the relevant gateway is configured in .env (see
.env.example — a [HUMAN] setup step); until then the buttons surface a
support-ready PaymentConfigError instead of crashing.
"""

import requests
import streamlit as st

from soulmatch import auth, billing, config, payments, theme
from soulmatch.db import get_session
from soulmatch.tenancy import owner_id_of

current_user = auth.require_login()
owner = owner_id_of(current_user)
plan = current_user.get("plan", "free")  # effective plan (paused -> "free")
actual_plan = current_user.get("actual_plan", plan)
plan_status = current_user.get("plan_status", "free")

theme.page_header("My Plan", "Your subscription, AI-action usage, and what each plan includes.")

with get_session() as session:
    status = billing.quota_status(session, current_user)

c1, c2 = st.columns([1, 2])
with c1:
    st.metric("Current plan", plan.capitalize())
    if plan_status == "paused":
        st.caption(f"Paused — your subscribed tier ({actual_plan.capitalize()}) resumes when you check out again.")
    elif plan_status == "past_due":
        st.caption("Payment failed — see the banner above.")
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

if actual_plan != "free" and plan_status == "active":
    if st.button("Pause subscription", help="Stops billing at the end of your current period. "
                                             "You'll gate as Free until you resume."):
        with get_session() as session:
            try:
                payments.cancel_subscription_at_period_end(session, owner)
                user_row = session.get(auth.User, owner)
                billing.pause_subscription(session, user_row)
            except (billing.PaymentConfigError, requests.RequestException) as e:
                st.error(str(e))
            else:
                st.success("Subscription paused. Resume anytime below.")
                st.rerun()

st.divider()
theme.section("Plans", "Pick a currency and billing interval, then upgrade below.")

currency = st.radio(
    "Currency", ["INR", "USD"], horizontal=True,
    help="Choose USD if you're paying from outside India (NRI).",
)
interval = st.radio("Billing", ["monthly", "annual"], horizontal=True)
price_table = billing.PLAN_PRICES_INR if currency == "INR" else billing.PLAN_PRICES_USD
price_table_annual = billing.PLAN_PRICES_INR_ANNUAL if currency == "INR" else billing.PLAN_PRICES_USD_ANNUAL
symbol = "₹" if currency == "INR" else "$"
period_label = "/mo" if interval == "monthly" else "/yr"

plan_cols = st.columns(3)
plan_details = [("free", "Free"), ("plus", "Plus"), ("pro", "Pro")]
for col, (plan_key, label) in zip(plan_cols, plan_details):
    limits = billing.limits_for(plan_key)
    price = (price_table_annual if interval == "annual" else price_table)[plan_key]
    with col:
        with st.container(border=True):
            is_current = plan_key == actual_plan
            st.markdown(f"### {label}" + (" ✅ current" if is_current else ""))
            st.markdown(f"**{symbol}{price}{period_label}**" if price else "**Free**")
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

            checkout_key = f"_checkout_url_{plan_key}_{interval}_{currency}"
            if plan_key == "free":
                if is_current:
                    st.caption("You're on Free.")
            elif is_current and plan_status == "paused":
                if st.button(f"Resume {label}", key=f"resume_{plan_key}", type="primary"):
                    with get_session() as session:
                        try:
                            if currency == "INR":
                                url = payments.create_razorpay_subscription_checkout(owner, plan_key, interval)
                            else:
                                url = payments.create_stripe_checkout_session(owner, plan_key, interval)
                        except (billing.PaymentConfigError, requests.RequestException) as e:
                            st.error(str(e))
                        else:
                            st.session_state[checkout_key] = url
            elif not is_current:
                if st.button(f"Upgrade to {label}" if price else f"Switch to {label}", key=f"upgrade_{plan_key}"):
                    with get_session() as session:
                        try:
                            if currency == "INR":
                                url = payments.create_razorpay_subscription_checkout(owner, plan_key, interval)
                            else:
                                url = payments.create_stripe_checkout_session(owner, plan_key, interval)
                        except (billing.PaymentConfigError, requests.RequestException) as e:
                            st.error(str(e))
                        else:
                            st.session_state[checkout_key] = url
            if st.session_state.get(checkout_key):
                st.link_button("Continue to checkout →", st.session_state[checkout_key], type="primary")

st.caption(
    "Payments are processed by Razorpay (India, UPI Autopay) or Stripe (international). "
    "Questions? support@redprana.com."
)
