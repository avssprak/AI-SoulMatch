"""V4-2-1 — the prime-profile page (the PDF's "Prime Profile Setup").

The member's child is the anchor everything else is scored against. If none
is marked yet, this page renders the shared 3-step wizard
(soulmatch/child_wizard.py — also embedded in the first-login onboarding
flow, pages_/00_Welcome.py, per V5-1-2, so there's one implementation of the
form, not two copies). Once one exists, this page becomes an anchor card
with inline edit and a guarded "change child" flow.
"""

from datetime import date

import streamlit as st
from sqlalchemy import select

from soulmatch import auth, theme
from soulmatch.child_wizard import render_wizard
from soulmatch.db import get_session
from soulmatch.horoscope_ui import compute_and_save_chart
from soulmatch.models import Profile
from soulmatch.nav import MATCHING_PAGE, next_step_button
from soulmatch.profiles import age_display, age_from_dob, is_match_ready, profile_completeness
from soulmatch.tenancy import get_owned, owned, owner_id_of
from soulmatch.ui import flash, show_flash

current_user = auth.require_login()
owner = owner_id_of(current_user)
can_write = auth.can_edit(current_user["role"])

theme.page_header("My Child", "The profile everything else is scored against.")
show_flash()

with get_session() as session:
    child = session.scalar(owned(select(Profile).where(Profile.is_own_child.is_(True)), Profile, owner))
    child_id = child.id if child else None

# ---------------------------------------------------------------------------
# No child marked yet — 3-step wizard
# ---------------------------------------------------------------------------
if child_id is None:
    if not can_write:
        st.info("No child profile has been set up yet. Your account has read-only access, so ask an editor to set one up.")
        st.stop()

    def _on_complete(profile: Profile) -> None:
        flash(f"{profile.full_name} is now set as your child's prime profile.")
        st.rerun()

    with get_session() as session:
        render_wizard(session, owner, current_user, on_complete=_on_complete)

# ---------------------------------------------------------------------------
# Child already marked — anchor card
# ---------------------------------------------------------------------------
else:
    with get_session() as session:
        child = get_owned(session, Profile, child_id, owner)
        percent, missing_fields = profile_completeness(child)
        match_ready = is_match_ready(child)

        with st.container(border=True):
            st.markdown(f"### 👑 {child.full_name or 'Unnamed'} — your prime profile")
            st.caption(
                f"{'Daughter' if child.gender == 'Bride' else 'Son'} · Age {age_display(child.dob, child.age)} · "
                f"{child.current_location or 'Location not set'} · {child.phone or 'No phone on file'}"
            )
            st.progress(
                percent / 100,
                text=f"Profile {percent}% complete"
                + (f" — missing {', '.join(missing_fields[:3])}" + ("…" if len(missing_fields) > 3 else "") if missing_fields else ""),
            )
            st.caption(
                "✅ Match-ready — has date, time & place of birth" if match_ready
                else "⚠️ Not match-ready — add date, time & place of birth below for a full astrology score"
            )
            st.caption("Everything under **Match & Compare** is scored against this profile.")
            next_step_button("Score candidates against this profile →", MATCHING_PAGE, key="my_child_score_btn")
            theme.help_link("child", "❓ Why does birth time matter?")

        if can_write:
            with st.expander("✏️ Edit details"):
                with st.form("my_child_edit"):
                    c1, c2, c3 = st.columns(3)
                    full_name = c1.text_input("Full Name", value=child.full_name or "")
                    current_location = c2.text_input("Current Location", value=child.current_location or "")
                    phone = c3.text_input("Phone", value=child.phone or "")
                    c1, c2, c3 = st.columns(3)
                    dob = c1.date_input(
                        "Date of Birth", value=child.dob, min_value=date(1930, 1, 1), max_value=date.today(),
                    )
                    birth_time = c2.text_input("Birth Time (24h HH:MM)", value=child.birth_time or "")
                    birth_place = c3.text_input("Birth Place", value=child.birth_place or "")
                    if st.form_submit_button("Save changes", type="primary"):
                        child.full_name = full_name or None
                        child.current_location = current_location or None
                        child.phone = phone or None
                        child.dob = dob
                        child.age = age_from_dob(dob) if dob else child.age
                        child.birth_time = birth_time or None
                        child.birth_place = birth_place or None
                        session.commit()
                        flash("Saved.")
                        st.rerun()

            if not child.horoscope_available or not match_ready:
                with st.expander("🔯 Compute horoscope", expanded=not match_ready):
                    compute_and_save_chart(session, owner, current_user, child, key_prefix="my_child")

            with st.expander("⚠️ Change child"):
                st.caption(
                    "Unmarks this profile as your child's prime profile (it stays in your candidate "
                    "list as a regular profile) so you can mark a different one, or set up a new one."
                )
                if st.button("Unmark as my child", key="my_child_unmark"):
                    child.is_own_child = False
                    session.commit()
                    flash(f"{child.full_name or 'This profile'} is no longer marked as your child.")
                    st.rerun()
