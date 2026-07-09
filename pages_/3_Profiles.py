import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch.db import get_session
from soulmatch.models import PIPELINE_STAGES, Activity, Profile

st.title("🗂️ Profiles")

tab_search, tab_manual = st.tabs(["Search & Manage", "Add Manually"])

with tab_search:
    col1, col2, col3, col4 = st.columns(4)
    gender_filter = col1.selectbox("Gender", ["All", "Bride", "Groom"])
    stage_filter = col2.selectbox("Stage", ["All"] + PIPELINE_STAGES)
    religion_filter = col3.text_input("Religion contains")
    location_filter = col4.text_input("Location contains")

    with get_session() as session:
        query = select(Profile)
        if gender_filter != "All":
            query = query.where(Profile.gender == gender_filter)
        if stage_filter != "All":
            query = query.where(Profile.stage == stage_filter)
        profiles = session.scalars(query.order_by(Profile.created_at.desc())).all()

    if religion_filter:
        profiles = [p for p in profiles if p.religion and religion_filter.lower() in p.religion.lower()]
    if location_filter:
        profiles = [p for p in profiles if p.current_location and location_filter.lower() in p.current_location.lower()]

    st.caption(f"{len(profiles)} profile(s)")

    if profiles:
        rows = [{
            "ID": p.id, "Name": p.full_name, "Gender": p.gender, "Age": p.age,
            "Religion": p.religion, "Caste": p.caste, "Location": p.current_location,
            "Qualification": p.qualification, "Occupation": p.occupation,
            "Stage": p.stage, "Horoscope": "Yes" if p.horoscope_available else "No",
        } for p in profiles]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        selected_id = st.selectbox(
            "View / edit a profile",
            options=[p.id for p in profiles],
            format_func=lambda pid: next(f"#{p.id} — {p.full_name or 'Unnamed'}" for p in profiles if p.id == pid),
        )

        with get_session() as session:
            profile = session.get(Profile, selected_id)

            with st.form("edit_profile"):
                c1, c2, c3 = st.columns(3)
                full_name = c1.text_input("Full Name", profile.full_name or "")
                gender = c2.selectbox("Gender", ["Bride", "Groom"], index=0 if profile.gender != "Groom" else 1)
                age = c3.number_input("Age", 18, 80, profile.age or 25)

                c1, c2, c3 = st.columns(3)
                religion = c1.text_input("Religion", profile.religion or "")
                caste = c2.text_input("Caste", profile.caste or "")
                gothram = c3.text_input("Gothram", profile.gothram or "")

                c1, c2, c3 = st.columns(3)
                qualification = c1.text_input("Qualification", profile.qualification or "")
                occupation = c2.text_input("Occupation", profile.occupation or "")
                current_location = c3.text_input("Current Location", profile.current_location or "")

                c1, c2, c3 = st.columns(3)
                dob = c1.date_input("Date of Birth", profile.dob)
                birth_time = c2.text_input("Birth Time (HH:MM)", profile.birth_time or "")
                birth_place = c3.text_input("Birth Place", profile.birth_place or "")

                c1, c2 = st.columns(2)
                height_cm = c1.number_input("Height (cm)", 100.0, 220.0, profile.height_cm or 165.0)
                food_preference = c2.selectbox(
                    "Food Preference", ["", "Vegetarian", "Non-Vegetarian", "Eggetarian"],
                    index=["", "Vegetarian", "Non-Vegetarian", "Eggetarian"].index(profile.food_preference or ""),
                )

                stage = st.selectbox("Pipeline Stage", PIPELINE_STAGES, index=PIPELINE_STAGES.index(profile.stage))
                notes = st.text_area("Notes", profile.notes or "")

                if st.form_submit_button("Save changes", type="primary"):
                    stage_changed = stage != profile.stage
                    profile.full_name = full_name or None
                    profile.gender = gender
                    profile.age = age
                    profile.religion = religion or None
                    profile.caste = caste or None
                    profile.gothram = gothram or None
                    profile.qualification = qualification or None
                    profile.occupation = occupation or None
                    profile.current_location = current_location or None
                    profile.dob = dob
                    profile.birth_time = birth_time or None
                    profile.birth_place = birth_place or None
                    profile.height_cm = height_cm
                    profile.food_preference = food_preference or None
                    profile.stage = stage
                    profile.notes = notes or None
                    if stage_changed:
                        session.add(Activity(profile_id=profile.id, event=f"Stage changed to {stage}"))
                    session.commit()
                    st.success("Saved.")
                    st.rerun()

            st.subheader("Activity Timeline")
            activities = session.scalars(
                select(Activity).where(Activity.profile_id == profile.id).order_by(Activity.created_at.desc())
            ).all()
            for a in activities:
                st.markdown(f"**{a.created_at:%d %b %Y, %H:%M}** — {a.event}" + (f": {a.detail}" if a.detail else ""))

            with st.form("add_activity"):
                event = st.text_input("Log new activity (e.g. 'Parents Contacted', 'Meeting Scheduled')")
                detail = st.text_input("Detail (optional)")
                if st.form_submit_button("Log activity"):
                    if event:
                        session.add(Activity(profile_id=profile.id, event=event, detail=detail or None))
                        session.commit()
                        st.rerun()
    else:
        st.info("No profiles match these filters.")

with tab_manual:
    with st.form("add_manual_profile"):
        c1, c2, c3 = st.columns(3)
        full_name = c1.text_input("Full Name*")
        gender = c2.selectbox("Gender*", ["Bride", "Groom"])
        age = c3.number_input("Age*", 18, 80, 25)

        c1, c2, c3 = st.columns(3)
        religion = c1.text_input("Religion")
        caste = c2.text_input("Caste")
        current_location = c3.text_input("Current Location")

        c1, c2 = st.columns(2)
        qualification = c1.text_input("Qualification")
        occupation = c2.text_input("Occupation")

        if st.form_submit_button("Create Profile", type="primary"):
            if not full_name:
                st.error("Full name is required.")
            else:
                with get_session() as session:
                    profile = Profile(
                        full_name=full_name, gender=gender, age=age,
                        religion=religion or None, caste=caste or None,
                        current_location=current_location or None,
                        qualification=qualification or None, occupation=occupation or None,
                        stage="New",
                    )
                    session.add(profile)
                    session.flush()
                    session.add(Activity(profile_id=profile.id, event="Profile Created", detail="Manual entry"))
                    session.commit()
                st.success(f"Created profile #{profile.id}.")
