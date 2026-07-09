from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import select

from soulmatch import auth
from soulmatch.db import get_session
from soulmatch.documents import DOCUMENT_KINDS, delete_document, read_document, save_document
from soulmatch.duplicates import find_duplicate_candidates
from soulmatch.models import PIPELINE_STAGES, STANDARD_TASK_TITLES, Activity, Document, Profile, Task, utcnow

current_user = auth.require_login()
can_write = auth.can_edit(current_user["role"])

st.title("🗂️ Profiles")
if not can_write:
    st.caption("Your account has read-only (Viewer) access.")

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
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

        selected_id = st.selectbox(
            "View / edit a profile",
            options=[p.id for p in profiles],
            format_func=lambda pid: next(f"#{p.id} — {p.full_name or 'Unnamed'}" for p in profiles if p.id == pid),
        )

        with get_session() as session:
            profile = session.get(Profile, selected_id)

            if can_write:
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
            else:
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Name:** {profile.full_name or '—'}")
                c2.markdown(f"**Gender:** {profile.gender or '—'}")
                c3.markdown(f"**Age:** {profile.age or '—'}")
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Religion:** {profile.religion or '—'}")
                c2.markdown(f"**Caste:** {profile.caste or '—'}")
                c3.markdown(f"**Gothram:** {profile.gothram or '—'}")
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**Qualification:** {profile.qualification or '—'}")
                c2.markdown(f"**Occupation:** {profile.occupation or '—'}")
                c3.markdown(f"**Location:** {profile.current_location or '—'}")
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**DOB:** {profile.dob or '—'}")
                c2.markdown(f"**Birth Time:** {profile.birth_time or '—'}")
                c3.markdown(f"**Birth Place:** {profile.birth_place or '—'}")
                st.markdown(f"**Stage:** {profile.stage}")
                if profile.notes:
                    st.markdown(f"**Notes:** {profile.notes}")

            st.subheader("Documents")
            existing_docs = session.scalars(
                select(Document).where(Document.profile_id == profile.id).order_by(Document.created_at.desc())
            ).all()
            if existing_docs:
                for doc in existing_docs:
                    dcol1, dcol2, dcol3 = st.columns([2, 2, 1])
                    dcol1.markdown(f"**{doc.kind}** — {doc.filename}")
                    try:
                        file_bytes = read_document(doc)
                        dcol2.download_button("Download", file_bytes, file_name=doc.filename, key=f"dl_{doc.id}")
                    except FileNotFoundError:
                        dcol2.caption("File missing on disk")
                    if can_write and dcol3.button("Delete", key=f"del_doc_{doc.id}"):
                        delete_document(session, doc)
                        session.commit()
                        st.rerun()
            else:
                st.caption("No documents uploaded yet.")

            if can_write:
                with st.form("upload_document", clear_on_submit=True):
                    doc_kind = st.selectbox("Document type", DOCUMENT_KINDS)
                    doc_file = st.file_uploader(
                        "File", type=["pdf", "jpg", "jpeg", "png"], key=f"doc_upload_{profile.id}"
                    )
                    if st.form_submit_button("Upload document"):
                        if doc_file is None:
                            st.warning("Choose a file first.")
                        else:
                            save_document(session, profile.id, doc_kind, doc_file.name, doc_file.read())
                            if doc_kind == "horoscope":
                                profile.horoscope_available = True
                            session.add(Activity(profile_id=profile.id, event="Document Uploaded",
                                                  detail=f"{doc_kind}: {doc_file.name}"))
                            session.commit()
                            st.rerun()

            st.subheader("Tasks")
            today = date.today()
            existing_tasks = session.scalars(
                select(Task).where(Task.profile_id == profile.id)
                .order_by(Task.status, Task.due_date.is_(None), Task.due_date)
            ).all()
            if existing_tasks:
                for task in existing_tasks:
                    tcol1, tcol2, tcol3 = st.columns([3, 1, 1])
                    label = f"**{task.title}**"
                    if task.due_date:
                        overdue = task.status == "Pending" and task.due_date < today
                        label += f" — due {task.due_date}" + (" ⚠️ overdue" if overdue else "")
                    label += f" ({task.status})"
                    tcol1.markdown(label)
                    if can_write and task.status == "Pending":
                        if tcol2.button("Done", key=f"task_done_{task.id}"):
                            task.status = "Done"
                            task.completed_at = utcnow()
                            session.add(Activity(profile_id=profile.id, event="Task completed",
                                                  detail=task.title))
                            session.commit()
                            st.rerun()
                        if tcol3.button("Cancel", key=f"task_cancel_{task.id}"):
                            task.status = "Cancelled"
                            session.commit()
                            st.rerun()
            else:
                st.caption("No tasks yet.")

            if can_write:
                with st.form("add_task", clear_on_submit=True):
                    tcol1, tcol2 = st.columns([2, 1])
                    title_choice = tcol1.selectbox("Task", STANDARD_TASK_TITLES + ["Custom..."])
                    custom_title = tcol1.text_input("Custom task title (if 'Custom...' selected)")
                    due = tcol2.date_input("Due date", value=None)
                    if st.form_submit_button("Add task"):
                        final_title = custom_title.strip() if title_choice == "Custom..." else title_choice
                        if not final_title:
                            st.warning("Enter a task title.")
                        else:
                            session.add(Task(profile_id=profile.id, title=final_title, due_date=due))
                            session.add(Activity(profile_id=profile.id, event="Task added", detail=final_title))
                            session.commit()
                            st.rerun()

            st.subheader("Activity Timeline")
            activities = session.scalars(
                select(Activity).where(Activity.profile_id == profile.id).order_by(Activity.created_at.desc())
            ).all()
            for a in activities:
                st.markdown(f"**{a.created_at:%d %b %Y, %H:%M}** — {a.event}" + (f": {a.detail}" if a.detail else ""))

            if can_write:
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
    if not can_write:
        st.info("Your account has read-only (Viewer) access.")
    else:
        with st.form("add_manual_profile"):
            c1, c2, c3 = st.columns(3)
            full_name = c1.text_input("Full Name*")
            gender = c2.selectbox("Gender*", ["Bride", "Groom"])
            age = c3.number_input("Age*", 18, 80, 25)

            c1, c2, c3 = st.columns(3)
            phone = c1.text_input("Phone")
            dob_input = c2.date_input("Date of Birth", value=None, min_value=date(1930, 1, 1), max_value=date.today())
            current_location = c3.text_input("Current Location")

            c1, c2, c3 = st.columns(3)
            religion = c1.text_input("Religion")
            caste = c2.text_input("Caste")
            gothram = c3.text_input("Gothram")

            c1, c2 = st.columns(2)
            qualification = c1.text_input("Qualification")
            occupation = c2.text_input("Occupation")

            submitted = st.form_submit_button("Check & Create Profile", type="primary")

        if submitted:
            if not full_name:
                st.error("Full name is required.")
            else:
                st.session_state["pending_manual_profile"] = dict(
                    full_name=full_name, gender=gender, age=age, phone=phone or None,
                    dob=dob_input, current_location=current_location or None,
                    religion=religion or None, caste=caste or None, gothram=gothram or None,
                    qualification=qualification or None, occupation=occupation or None,
                )

        pending = st.session_state.get("pending_manual_profile")
        if pending:
            with get_session() as session:
                duplicates = find_duplicate_candidates(
                    session, full_name=pending["full_name"], gender=pending["gender"],
                    phone=pending["phone"], dob=pending["dob"],
                )
            if duplicates:
                st.warning(f"⚠️ {len(duplicates)} possible duplicate(s) found:")
                for d in duplicates[:5]:
                    st.markdown(f"- **#{d.profile.id} {d.profile.full_name or 'Unnamed'}** "
                                f"({d.score}% match) — {'; '.join(d.reasons)}")
            else:
                st.success("No duplicates found.")

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Create profile" + (" anyway" if duplicates else ""), type="primary"):
                    with get_session() as session:
                        profile = Profile(stage="New", **pending)
                        session.add(profile)
                        session.flush()
                        session.add(Activity(profile_id=profile.id, event="Profile Created", detail="Manual entry"))
                        session.commit()
                        new_id = profile.id
                    del st.session_state["pending_manual_profile"]
                    st.success(f"Created profile #{new_id}.")
            with col2:
                if st.button("Cancel"):
                    del st.session_state["pending_manual_profile"]
                    st.rerun()
