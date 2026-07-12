"""V4-2-1 — the prime-profile page (the PDF's "Prime Profile Setup").

The member's child is the anchor everything else is scored against. If none
is marked yet, this page is a short 3-step wizard that creates a normal
owned Profile with is_own_child=True (same flag pages_/3_Profiles.py already
toggles — this page is just a friendlier front door onto it, not a new
concept). Once one exists, this page becomes an anchor card with inline
edit and a guarded "change child" flow.
"""

from datetime import date

import streamlit as st
from sqlalchemy import select

from soulmatch import auth, billing, theme
from soulmatch.db import get_session
from soulmatch.horoscope_ui import compute_and_save_chart
from soulmatch.models import Activity, Profile
from soulmatch.nav import MATCHING_PAGE, next_step_button
from soulmatch.profiles import age_from_dob, is_match_ready, profile_completeness
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

WIZARD_STEP_KEY = "my_child_wizard_step"
WIZARD_DATA_KEY = "my_child_wizard_data"


def _reset_wizard() -> None:
    st.session_state.pop(WIZARD_STEP_KEY, None)
    st.session_state.pop(WIZARD_DATA_KEY, None)


# ---------------------------------------------------------------------------
# No child marked yet — 3-step wizard
# ---------------------------------------------------------------------------
if child_id is None:
    if not can_write:
        st.info("No child profile has been set up yet. Your account has read-only access, so ask an editor to set one up.")
        st.stop()

    step = st.session_state.get(WIZARD_STEP_KEY, 1)
    data = st.session_state.setdefault(WIZARD_DATA_KEY, {})

    theme.journey_stepper([
        (step > 1, "Details"),
        (step > 2, "Birth details"),
        (step > 3, "Confirm"),
    ])

    if step == 1:
        theme.section("Step 1 · Details", "Who are we finding a match for?")
        with st.form("my_child_step1"):
            full_name = st.text_input("Full Name*", value=data.get("full_name", ""))
            c1, c2 = st.columns(2)
            gender = c1.selectbox(
                "This is my…", ["Daughter", "Son"],
                index=0 if data.get("gender", "Bride") == "Bride" else 1,
                help="Candidates you add later will be matched from the opposite pool automatically.",
            )
            current_location = c2.text_input("Current Location", value=data.get("current_location", ""))
            phone = st.text_input("Phone (optional)", value=data.get("phone", ""))
            submitted = st.form_submit_button("Next →", type="primary")
        if submitted:
            if not full_name.strip():
                st.error("Full name is required.")
            else:
                data.update(
                    full_name=full_name.strip(),
                    gender="Bride" if gender == "Daughter" else "Groom",
                    current_location=current_location or None,
                    phone=phone or None,
                )
                st.session_state[WIZARD_STEP_KEY] = 2
                st.rerun()

    elif step == 2:
        theme.section("Step 2 · Birth details", "Add these now for a full horoscope-based match score — or skip and add them later.")
        with st.form("my_child_step2"):
            c1, c2, c3 = st.columns(3)
            dob = c1.date_input(
                "Date of Birth", value=data.get("dob"), min_value=date(1930, 1, 1),
                max_value=date.today(),
            )
            birth_time = c2.text_input("Birth Time (24h HH:MM)", value=data.get("birth_time", ""))
            birth_place = c3.text_input("Birth Place", value=data.get("birth_place", ""))
            bc1, bc2 = st.columns(2)
            back = bc1.form_submit_button("← Back")
            forward = bc2.form_submit_button("Next →", type="primary")
        if back:
            st.session_state[WIZARD_STEP_KEY] = 1
            st.rerun()
        if forward:
            data.update(dob=dob, birth_time=birth_time or None, birth_place=birth_place or None)
            st.session_state[WIZARD_STEP_KEY] = 3
            st.rerun()

    elif step == 3:
        theme.section("Step 3 · Confirm", "Review before saving as your child's prime profile.")
        st.markdown(
            f"- **Name:** {data['full_name']}\n"
            f"- **Gender:** {'Daughter' if data['gender'] == 'Bride' else 'Son'}\n"
            f"- **Location:** {data.get('current_location') or '—'}\n"
            f"- **Phone:** {data.get('phone') or '—'}\n"
            f"- **DOB:** {data.get('dob') or '—'}\n"
            f"- **Birth Time:** {data.get('birth_time') or '—'}\n"
            f"- **Birth Place:** {data.get('birth_place') or '—'}"
        )
        bc1, bc2, bc3 = st.columns([1, 1, 2])
        if bc1.button("← Back"):
            st.session_state[WIZARD_STEP_KEY] = 2
            st.rerun()
        if bc2.button("Confirm & Save", type="primary"):
            with get_session() as session:
                can_add, cap_message = billing.can_add_profile(session, current_user)
                can_mark, mark_message = billing.can_mark_own_child(session, current_user)
                if not can_add:
                    st.warning(cap_message)
                elif not can_mark:
                    st.warning(mark_message)
                else:
                    profile = Profile(
                        full_name=data["full_name"], gender=data["gender"],
                        age=age_from_dob(data["dob"]) if data.get("dob") else None,
                        dob=data.get("dob"), birth_time=data.get("birth_time"),
                        birth_place=data.get("birth_place"),
                        current_location=data.get("current_location"), phone=data.get("phone"),
                        stage="New", is_own_child=True, owner_user_id=owner,
                    )
                    session.add(profile)
                    session.flush()
                    session.add(Activity(
                        profile_id=profile.id, owner_user_id=owner, event="Profile Created",
                        detail="My Child wizard", created_by_user_id=current_user["id"],
                    ))
                    session.commit()
                    _reset_wizard()
                    flash(f"{profile.full_name} is now set as your child's prime profile.")
                    st.rerun()

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
                f"{'Daughter' if child.gender == 'Bride' else 'Son'} · Age {child.age or '—'} · "
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
