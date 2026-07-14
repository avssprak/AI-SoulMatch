"""V5-1-2 — first-login onboarding wizard.

Not registered in app.py's `sections` nav — the only way here is the
redirect in app.py (unonboarded member on any other page) or the "My Plan"
skip link's target being elsewhere. Deliberately hidden: this is a one-time
front door, not a page a returning member should stumble back into.

Three steps, reusing existing building blocks so this is glue, not new UI:
1. Welcome — three cards explaining the journey (no state, just a "Let's go"
   button into step 2).
2. My Child — soulmatch.child_wizard's shared 3-step form (same one
   pages_/0_My_Child.py uses standalone).
3. Done — set onboarded_at, offer "Add your first candidate" or "Explore
   the dashboard".

A quiet "Skip for now" link is available on every step — it sets
onboarded_at and leaves for the Dashboard immediately. Never trap the user.
"""

import streamlit as st
from sqlalchemy import select

from soulmatch import auth, theme
from soulmatch.child_wizard import render_wizard
from soulmatch.db import get_session
from soulmatch.models import Profile
from soulmatch.nav import DASHBOARD_PAGE, INGEST_PAGE
from soulmatch.tenancy import owned, owner_id_of

current_user = auth.require_login()
owner = owner_id_of(current_user)
can_write = auth.can_edit(current_user["role"])

WELCOME_STEP_KEY = "_welcome_step"


def _mark_onboarded() -> None:
    # app.py recomputes `needs_onboarding` fresh from the DB on the very next
    # rerun (triggered by the switch_page() every caller does right after
    # this), so there's nothing else to update in session_state here.
    with get_session() as session:
        auth.mark_onboarded(session, session.get(auth.User, owner))


def _skip_link(key: str) -> None:
    if st.button("Skip for now", key=key, type="tertiary"):
        _mark_onboarded()
        st.switch_page(DASHBOARD_PAGE)


theme.page_header("Welcome to SoulMatch", "A quick 2-minute setup, then you're on your own.")

with get_session() as session:
    existing_child = session.scalar(
        owned(select(Profile).where(Profile.is_own_child.is_(True)), Profile, owner)
    )

# A Viewer-role account (or a Member who somehow already has a child, e.g.
# restored from an export) has nothing to do here — send them straight in.
if not can_write or existing_child is not None:
    _mark_onboarded()
    st.switch_page(DASHBOARD_PAGE)

step = st.session_state.get(WELCOME_STEP_KEY, 1)

if step == 1:
    theme.section("How SoulMatch works", "Four steps, in order — the sidebar follows the same shape.")
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        st.markdown("**1. Tell us about your child**")
        st.caption("Their basics and birth details — everything else is scored against this profile.")
    with c2, st.container(border=True):
        st.markdown("**2. Add candidates**")
        st.caption("Paste a WhatsApp chat or biodata, or add one by hand.")
    with c3, st.container(border=True):
        st.markdown("**3. Get match scores**")
        st.caption("Horoscope compatibility + practical fit, blended into one score.")
    st.write("")
    bc1, bc2 = st.columns([1, 3])
    if bc1.button("Set up my child →", type="primary", key="welcome_start"):
        st.session_state[WELCOME_STEP_KEY] = 2
        st.rerun()
    with bc2:
        _skip_link("welcome_skip_1")

elif step == 2:
    def _on_child_saved(profile: Profile) -> None:
        st.session_state[WELCOME_STEP_KEY] = 3
        st.rerun()

    with get_session() as session:
        render_wizard(session, owner, current_user, on_complete=_on_child_saved)
    st.write("")
    _skip_link("welcome_skip_2")

elif step == 3:
    _mark_onboarded()
    theme.section("You're all set", "Your child's profile is saved — everything else is scored against it.")
    st.success("🎉 Now let's find some candidates.")
    c1, c2 = st.columns(2)
    if c1.button("Add your first candidate →", type="primary", key="welcome_done_ingest"):
        st.switch_page(INGEST_PAGE)
    if c2.button("Explore the dashboard", key="welcome_done_dashboard"):
        st.switch_page(DASHBOARD_PAGE)
