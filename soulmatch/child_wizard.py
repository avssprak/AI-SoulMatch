"""V5-1-2: the 3-step "who are we finding a match for?" wizard, extracted out
of pages_/0_My_Child.py so pages_/00_Welcome.py can embed the same flow
instead of copy-pasting the form code. Session-state keys are shared across
callers deliberately — only one of these pages is ever on screen at a time,
so there's no risk of two wizards fighting over the same in-progress state.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

import streamlit as st
from sqlalchemy.orm import Session

from soulmatch import billing, theme
from soulmatch.models import Activity, Profile
from soulmatch.profiles import age_from_dob

WIZARD_STEP_KEY = "my_child_wizard_step"
WIZARD_DATA_KEY = "my_child_wizard_data"


def reset_wizard() -> None:
    st.session_state.pop(WIZARD_STEP_KEY, None)
    st.session_state.pop(WIZARD_DATA_KEY, None)


def render_wizard(
    session: Session, owner: int, current_user: dict, *, on_complete: Callable[[Profile], None] | None = None,
) -> None:
    """Render the current wizard step. Call only when no child profile exists
    yet and the caller has already confirmed `auth.can_edit(current_user["role"])`.
    On save, creates the Profile, logs the Activity, resets the wizard state,
    and calls `on_complete(profile)` if given (pages_/0_My_Child.py flashes
    and reruns in place; pages_/00_Welcome.py instead advances its own step)."""
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
                reset_wizard()
                if on_complete is not None:
                    on_complete(profile)
                else:
                    st.rerun()
