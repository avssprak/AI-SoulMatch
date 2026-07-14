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
from soulmatch.export import delete_owner_account, export_owner_data_zip
from soulmatch.tenancy import owner_id_of
from soulmatch.timezones import COMMON_TIMEZONES, DEFAULT_TIMEZONE

current_user = auth.require_login()
owner = owner_id_of(current_user)
plan = current_user.get("plan", "free")  # effective plan (paused -> "free")
actual_plan = current_user.get("actual_plan", plan)
plan_status = current_user.get("plan_status", "free")
current_timezone = current_user.get("timezone", DEFAULT_TIMEZONE)

theme.page_header("My Plan & Settings", "Your subscription, AI-action usage, and what each plan includes.")
theme.help_link("billing", "❓ Billing questions?")

with get_session() as session:
    status = billing.quota_status(session, current_user)
    profile_usage = billing.profile_usage_status(session, current_user)
    current_billing_interval = payments.current_billing_interval(session, owner)

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

    monthly_limit_text = "Unlimited" if profile_usage.monthly_limit is None else str(profile_usage.monthly_limit)
    st.markdown(f"**Profiles added this month:** {profile_usage.used_this_month} / {monthly_limit_text}")
    if profile_usage.monthly_limit is not None:
        st.progress(min(profile_usage.used_this_month / profile_usage.monthly_limit, 1.0))
    total_limit_text = "unlimited" if profile_usage.total_limit is None else str(profile_usage.total_limit)
    st.caption(f"{profile_usage.total} / {total_limit_text} total profiles stored · resets on {profile_usage.resets_on:%d %b %Y}.")

st.divider()
theme.section("Account settings")

tz_options = COMMON_TIMEZONES if current_timezone in COMMON_TIMEZONES else [current_timezone, *COMMON_TIMEZONES]
new_timezone = st.selectbox(
    "Your timezone", tz_options, index=tz_options.index(current_timezone),
    help="Dates and times across the app are shown in this timezone. Data is always stored in UTC.",
)
if new_timezone != current_timezone:
    with get_session() as session:
        user_row = session.get(auth.User, owner)
        user_row.timezone = new_timezone
        session.commit()
    # Also update the session copy — app.py only refreshes it on full page
    # loads, and rerunning with a stale value here would loop forever.
    current_user["timezone"] = new_timezone
    st.session_state["user"] = current_user
    st.success(f"Timezone updated to {new_timezone}.")
    st.rerun()

# V5-4-1: moved here from a sidebar expander so account settings live in one
# place instead of being split between the sidebar and this page.
with st.expander("Change password"):
    with st.form("change_password", clear_on_submit=True):
        old_pw = st.text_input("Current password", type="password")
        new_pw = st.text_input("New password", type="password")
        if st.form_submit_button("Update password"):
            with get_session() as session:
                user_row = session.get(auth.User, owner)
                if not auth.verify_password(old_pw, user_row.password_hash):
                    st.error("Current password is incorrect.")
                else:
                    try:
                        auth.change_password(session, user_row, new_pw)
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        # re-mint immediately so the current session (which
                        # still has the old token in the URL) isn't logged
                        # out too
                        st.query_params["token"] = auth.mint_session_token(user_row)
                        st.success("Password updated.")

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
            # V5-7: "current" must match both plan AND billing interval — a
            # member on Plus Monthly viewing the Annual toggle is still on
            # Plus, but not on *this* Plus card's interval, so it must offer
            # a switch-billing button instead of silently showing no action
            # (the bug: only Pro showed an "Upgrade" button in that case).
            is_current_plan = plan_key == actual_plan
            is_current_exact = is_current_plan and (plan_key == "free" or current_billing_interval == interval)
            st.markdown(f"### {label}" + (" ✅ current" if is_current_exact else ""))
            if is_current_plan and not is_current_exact and plan_key != "free":
                st.caption(f"Your current plan — billed {current_billing_interval or 'monthly'}.")
            st.markdown(f"**{symbol}{price}{period_label}**" if price else "**Free**")
            if interval == "annual" and price:
                st.caption(f"Approx {billing.annual_discount_pct(plan_key, currency)}% off vs. paying monthly.")
            st.markdown(f"- {limits['ai_actions']} AI actions/mo")
            st.markdown(
                "- " + ("Unlimited profiles" if limits["profiles"] is None else f"{limits['profiles']} profiles")
            )
            st.markdown(f"- Up to {limits['profiles_per_month']} new profiles/month")
            st.markdown(f"- {limits['children']} child/children")
            st.markdown("- " + ("✅" if limits["ai_explanations"] else "❌") + " AI match explanations")
            st.markdown("- " + ("✅" if limits["nl_search"] else "❌") + " Natural-language search")
            bulk = limits["bulk_imports"]
            st.markdown(
                "- " + ("Unlimited bulk imports" if bulk is None else f"{bulk} bulk import(s)/mo" if bulk else "No bulk import")
            )

            checkout_key = f"_checkout_url_{plan_key}_{interval}_{currency}"

            def _start_checkout(*, cancel_existing: bool) -> None:
                with get_session() as session:
                    try:
                        url = payments.start_checkout(
                            session, owner, plan_key, interval, currency, cancel_existing=cancel_existing,
                        )
                    except (billing.PaymentConfigError, requests.RequestException) as e:
                        st.error(str(e))
                    else:
                        st.session_state[checkout_key] = url

            if plan_key == "free":
                if is_current_exact:
                    st.caption("You're on Free.")
            elif is_current_exact and plan_status == "paused":
                # The old subscription is already being wound down by the
                # earlier Pause action (cancel_subscription_at_period_end) —
                # nothing further to cancel here.
                if st.button(f"Resume {label}", key=f"resume_{plan_key}", type="primary"):
                    _start_checkout(cancel_existing=False)
            elif is_current_plan and not is_current_exact:
                # Same plan, different billing interval — e.g. Plus Monthly
                # viewing the Annual toggle. cancel_existing=True stops the
                # Monthly subscription renewing before starting the Annual
                # one, so the member is never being billed on both at once.
                switch_label = "Switch to annual billing" if interval == "annual" else "Switch to monthly billing"
                if st.button(switch_label, key=f"switch_interval_{plan_key}"):
                    _start_checkout(cancel_existing=True)
            elif not is_current_plan:
                # A different plan entirely — same double-billing risk as an
                # interval switch if the member is already paying for
                # something else, so cancel that first too.
                if st.button(f"Upgrade to {label}" if price else f"Switch to {label}", key=f"upgrade_{plan_key}"):
                    _start_checkout(cancel_existing=True)
            if st.session_state.get(checkout_key):
                st.link_button("Continue to checkout →", st.session_state[checkout_key], type="primary")

st.caption(
    "Payments are processed by Razorpay (India, UPI Autopay) or Stripe (international). "
    "Questions? support@redprana.com."
)

st.divider()
theme.section("Your data", "Export everything, or permanently delete your account (V3-5-2).")

dcol1, dcol2 = st.columns(2)
with dcol1:
    st.markdown("**Export my data**")
    st.caption("A ZIP with every profile, document, task, and activity your account has stored.")
    if st.button("Prepare export"):
        with get_session() as session:
            st.session_state["_export_zip"] = export_owner_data_zip(session, owner)
    if st.session_state.get("_export_zip"):
        st.download_button(
            "⬇️ Download my data (.zip)", st.session_state["_export_zip"],
            file_name="soulmatch_export.zip", mime="application/zip",
        )

with dcol2:
    st.markdown("**Delete my account**")
    st.caption("Permanently deletes your account and everything in it. This cannot be undone.")
    with st.expander("Delete my account"):
        st.error(
            "This permanently deletes your account, every profile, document, task, and "
            "match result you own. There is no undo."
        )
        confirm_text = st.text_input("Type DELETE to confirm", key="delete_account_confirm")
        if st.button("Permanently delete my account", type="primary", disabled=confirm_text != "DELETE"):
            with get_session() as session:
                user_row = session.get(auth.User, owner)
                if auth.is_last_admin(session, user_row):
                    st.error(
                        "You're the only Administrator account — deleting it would lock the "
                        "platform out of its own operator tools. Promote another account to "
                        "Admin first, or contact support@redprana.com."
                    )
                else:
                    delete_owner_account(session, owner)
                    del st.session_state["user"]
                    if "token" in st.query_params:
                        del st.query_params["token"]
                    st.success("Your account has been deleted.")
                    st.rerun()
