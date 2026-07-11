from datetime import date, time as dt_time

import pandas as pd
import streamlit as st
from sqlalchemy import or_, select

from soulmatch import auth
from soulmatch.astrology.geo import lookup as geo_lookup
from soulmatch.db import get_session
from soulmatch.documents import DOCUMENT_KINDS, delete_document, read_document, save_document
from soulmatch.duplicates import find_all_duplicate_pairs, find_duplicate_candidates, merge_profiles
from soulmatch.extraction.llm import LLMError
from soulmatch.matchview import render_saved_match_result
from soulmatch.models import (
    PIPELINE_STAGES, STANDARD_TASK_TITLES, Activity, Document, MatchResult, Profile, Task, User,
    stage_group_label, utcnow,
)
from soulmatch.nav import consume_open_profile_request
from soulmatch.profiles import age_from_dob, delete_profile, is_match_ready, profile_completeness
from soulmatch.search import describe_filters, parse_query
from soulmatch.summary import profile_summary_html
from soulmatch import theme
from soulmatch.ui import flash, show_flash, stage_badge

IMAGE_DOC_EXTENSIONS = (".jpg", ".jpeg", ".png")
# Parsed-query fields with no dedicated filter widget on this page — applied
# directly to the result list instead of a UI control (age range, caste,
# food preference, etc.), shown back to the user as a caption rather than
# silently dropped.
NL_EXTRA_FILTER_KEYS = [
    "min_age", "max_age", "caste", "qualification_contains", "occupation_contains",
    "food_preference", "marital_status", "horoscope_available",
]


def _parse_birth_time(value: str | None) -> dt_time | None:
    """'HH:MM' stored string -> time object for st.time_input's value=."""
    if not value:
        return None
    try:
        hour, minute = value.split(":")
        return dt_time(int(hour), int(minute))
    except (ValueError, TypeError):
        return None


@st.dialog("Profile Summary", width="large")
def _print_summary_dialog(profile: Profile, photo_bytes: bytes | None) -> None:
    chart = (
        {"nakshatra": profile.nakshatra, "rashi": profile.rashi, "lagna": profile.lagna}
        if (profile.nakshatra or profile.rashi or profile.lagna) else None
    )
    html = profile_summary_html(profile, photo_bytes=photo_bytes, chart=chart)
    st.caption("Use your browser's Print (Ctrl/Cmd+P) to print or save as PDF, or download the HTML below.")
    st.html(html)
    file_stub = (profile.full_name or "profile").replace(" ", "_")
    st.download_button(
        "⬇️ Download as HTML", html.encode("utf-8"),
        file_name=f"{file_stub}_summary.html", mime="text/html", key=f"download_summary_{profile.id}",
    )

current_user = auth.require_login()
can_write = auth.can_edit(current_user["role"])

theme.page_header("Profiles", "Every bride and groom in your practice — browse, edit, and track each case.")
show_flash()
if not can_write:
    st.caption("Your account has read-only (Viewer) access.")

# A widget's session_state can only be written before that widget is instantiated
# in a given run — so a delete/merge handler further down the script can't reset
# "profiles_table"'s selection directly (the dataframe below already renders it
# this run). It sets this flag and reruns instead; we consume it here, before
# the table widget exists for the new run, avoiding a stale-row-index crash
# after the table shrinks.
if st.session_state.pop("_clear_profiles_selection", False):
    st.session_state["profiles_table"] = {"selection": {"rows": [], "columns": [], "cells": []}}

# Deep-linked from another page (e.g. Search, Dashboard, Tasks) via
# soulmatch.nav.request_open_profile — same reason as above: must be consumed
# before the table widget below is instantiated for this run.
deep_link_profile_id = consume_open_profile_request()

tab_search, tab_manual, tab_duplicates = st.tabs(["Search & Manage", "Add Manually", "🔍 Find Duplicate Profiles"])

with tab_search:
    # A natural-language query prefills the structured filter widgets below
    # (still visible + editable) rather than replacing them — the filters
    # stay the single source of truth. Widget session_state can only be
    # written before that widget is instantiated, so the prefill is consumed
    # here, at the very top, same deferred-flag pattern as elsewhere on this
    # page.
    nl_prefill = st.session_state.pop("_nl_prefill", None)
    if nl_prefill:
        for widget_key, value in nl_prefill.items():
            st.session_state[widget_key] = value

    with st.expander(
        "🔎 Search in plain English (optional)",
        expanded=bool(st.session_state.get("_nl_extra_filters")),
    ):
        st.caption(
            "Describe who you're looking for — fills in the filters below, and applies a few "
            "extra ones directly (age range, food preference, horoscope status, ...)."
        )
        nl_col1, nl_col2 = st.columns([4, 1])
        nl_query = nl_col1.text_input(
            "Describe who you're looking for", key="profiles_nl_query", label_visibility="collapsed",
            placeholder='e.g. "Brahmin brides in Bangalore under 28 with a horoscope"',
        )
        if nl_col2.button("Apply", key="profiles_nl_apply") and nl_query.strip():
            with get_session() as nl_session:
                try:
                    nl_filters = parse_query(nl_session, nl_query)
                except LLMError as e:
                    st.error(str(e))
                    nl_filters = None
            if nl_filters:
                prefill = {}
                if nl_filters.get("gender") in ("Bride", "Groom"):
                    prefill["pf_gender"] = nl_filters["gender"]
                if nl_filters.get("religion"):
                    prefill["pf_religion"] = nl_filters["religion"]
                if nl_filters.get("current_location"):
                    prefill["pf_location"] = nl_filters["current_location"]
                if nl_filters.get("stage"):
                    prefill["pf_stage"] = nl_filters["stage"]
                extra = {k: nl_filters.get(k) for k in NL_EXTRA_FILTER_KEYS if nl_filters.get(k) is not None}
                st.session_state["_nl_prefill"] = prefill
                st.session_state["_nl_extra_filters"] = extra
                flash(f"Parsed as: {describe_filters(nl_filters)}")
                st.rerun()

        nl_extra_active = st.session_state.get("_nl_extra_filters")
        if nl_extra_active:
            ec1, ec2 = st.columns([5, 1])
            ec1.caption(f"Also applied directly: {describe_filters(nl_extra_active)}")
            if ec2.button("Clear", key="clear_nl_extra"):
                st.session_state.pop("_nl_extra_filters", None)
                st.rerun()

    col1, col2, col3, col4, col5 = st.columns(5)
    name_filter = col1.text_input("Name contains", key="pf_name")
    gender_filter = col2.selectbox("Gender", ["All", "Bride", "Groom"], key="pf_gender")
    stage_filter = col3.selectbox(
        "Stage", ["All"] + PIPELINE_STAGES,
        format_func=lambda s: s if s == "All" else stage_group_label(s), key="pf_stage",
    )
    religion_filter = col4.text_input("Religion contains", key="pf_religion")
    location_filter = col5.text_input("Location contains", key="pf_location")
    match_ready_filter = st.radio(
        "Birth details", ["All", "Match-ready", "Missing"], horizontal=True,
        help="Match-ready = has date, time, and place of birth — enough for a full astrology score.",
    )

    with get_session() as session:
        query = select(Profile)
        if gender_filter != "All":
            query = query.where(Profile.gender == gender_filter)
        if stage_filter != "All":
            query = query.where(Profile.stage == stage_filter)
        profiles = session.scalars(query.order_by(Profile.created_at.desc())).all()

    if name_filter:
        profiles = [p for p in profiles if p.full_name and name_filter.lower() in p.full_name.lower()]
    if religion_filter:
        profiles = [p for p in profiles if p.religion and religion_filter.lower() in p.religion.lower()]
    if location_filter:
        profiles = [p for p in profiles if p.current_location and location_filter.lower() in p.current_location.lower()]
    if match_ready_filter != "All":
        want_ready = match_ready_filter == "Match-ready"
        profiles = [p for p in profiles if is_match_ready(p) == want_ready]

    nl_extra = st.session_state.get("_nl_extra_filters") or {}
    if nl_extra.get("min_age") is not None:
        profiles = [p for p in profiles if p.age is not None and p.age >= nl_extra["min_age"]]
    if nl_extra.get("max_age") is not None:
        profiles = [p for p in profiles if p.age is not None and p.age <= nl_extra["max_age"]]
    if nl_extra.get("caste"):
        needle = nl_extra["caste"].lower()
        profiles = [p for p in profiles if p.caste and needle in p.caste.lower()]
    if nl_extra.get("qualification_contains"):
        needle = nl_extra["qualification_contains"].lower()
        profiles = [p for p in profiles if p.qualification and needle in p.qualification.lower()]
    if nl_extra.get("occupation_contains"):
        needle = nl_extra["occupation_contains"].lower()
        profiles = [p for p in profiles if p.occupation and needle in p.occupation.lower()]
    if nl_extra.get("food_preference"):
        profiles = [p for p in profiles if p.food_preference == nl_extra["food_preference"]]
    if nl_extra.get("marital_status"):
        profiles = [p for p in profiles if p.marital_status == nl_extra["marital_status"]]
    if nl_extra.get("horoscope_available") is not None:
        profiles = [p for p in profiles if bool(p.horoscope_available) == nl_extra["horoscope_available"]]

    st.caption(f"{len(profiles)} profile(s)")

    if profiles:
        rows = [{
            "ID": p.id, "Name": p.full_name, "Gender": p.gender, "Age": p.age,
            "Religion": p.religion, "Caste": p.caste, "Location": p.current_location,
            "Qualification": p.qualification, "Occupation": p.occupation,
            "Stage": p.stage, "Horoscope": "Yes" if p.horoscope_available else "No",
        } for p in profiles]
        st.download_button(
            "⬇️ Export as CSV", pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
            file_name="profiles.csv", mime="text/csv", key="export_profiles_csv",
        )
        table_event = st.dataframe(
            pd.DataFrame(rows), width='stretch', hide_index=True,
            on_select="rerun", selection_mode="multi-row", key="profiles_table",
        )
        st.caption("Tip: click a row to select that profile below — ctrl/shift-click to select several to bulk-delete.")
        selected_rows = table_event.selection.rows if table_event and table_event.selection else []
        row_selected_id = rows[selected_rows[0]]["ID"] if selected_rows else None
        selected_ids = [rows[i]["ID"] for i in selected_rows]

        if can_write and len(selected_ids) > 1:
            bulk_confirm_key = "confirm_bulk_delete_profiles"
            if bulk_confirm_key in st.session_state:
                st.error(f"Really delete {len(selected_ids)} selected profile(s)? This cannot be undone.")
                with st.container(horizontal=True):
                    if st.button("Yes, delete all selected", key="confirm_bulk_delete_btn", type="primary"):
                        with get_session() as bulk_session:
                            deleted = 0
                            for pid in selected_ids:
                                target = bulk_session.get(Profile, pid)
                                if target:
                                    delete_profile(bulk_session, target)
                                    deleted += 1
                        del st.session_state[bulk_confirm_key]
                        st.session_state["_clear_profiles_selection"] = True
                        flash(f"Deleted {deleted} profile(s).")
                        st.rerun()
                    if st.button("Cancel", key="cancel_bulk_delete_btn"):
                        del st.session_state[bulk_confirm_key]
                        st.rerun()
            elif st.button(f"🗑️ Delete {len(selected_ids)} selected profile(s)", key="bulk_delete_profiles_btn"):
                st.session_state[bulk_confirm_key] = True
                st.rerun()

        options = [p.id for p in profiles]
        preferred_id = deep_link_profile_id if deep_link_profile_id in options else row_selected_id
        default_index = options.index(preferred_id) if preferred_id in options else 0
        selected_id = st.selectbox(
            "View / edit a profile",
            options=options,
            index=default_index,
            format_func=lambda pid: next(f"#{p.id} — {p.full_name or 'Unnamed'}" for p in profiles if p.id == pid),
            key=f"profile_select_{preferred_id}",
        )

        with get_session() as session:
            profile = session.get(Profile, selected_id)

            # --- Header card: photo, badge, completeness, quick stage move ---
            percent, missing_fields = profile_completeness(profile)
            match_ready = is_match_ready(profile)
            photo_doc = session.scalars(
                select(Document).where(Document.profile_id == profile.id, Document.kind == "photo")
                .order_by(Document.created_at.desc())
            ).first()

            with st.container(border=True):
                hcol1, hcol2 = st.columns([1, 4])
                with hcol1:
                    if photo_doc:
                        try:
                            st.image(read_document(photo_doc), width=120)
                        except FileNotFoundError:
                            st.caption("📷 photo file missing")
                    else:
                        st.caption("📷 No photo yet — add one under Documents.")
                with hcol2:
                    st.markdown(f"### #{profile.id} — {profile.full_name or 'Unnamed'}  {stage_badge(profile.stage)}")
                    st.caption(
                        f"{profile.gender or '—'} · Age {profile.age or '—'} · "
                        f"{profile.current_location or 'Location not set'} · {profile.phone or 'No phone on file'}"
                    )
                    st.progress(
                        percent / 100,
                        text=f"Profile {percent}% complete"
                        + (f" — missing {', '.join(missing_fields[:3])}"
                           + ("…" if len(missing_fields) > 3 else "") if missing_fields else ""),
                    )
                    st.caption(
                        "✅ Match-ready — has date, time & place of birth" if match_ready
                        else "⚠️ Not match-ready — add date, time & place of birth for a full astrology score"
                    )
                    if st.button("📄 Print / download summary", key=f"print_summary_{profile.id}"):
                        photo_bytes = None
                        if photo_doc:
                            try:
                                photo_bytes = read_document(photo_doc)
                            except FileNotFoundError:
                                photo_bytes = None
                        _print_summary_dialog(profile, photo_bytes)

                if can_write:
                    qc1, qc2 = st.columns([3, 1])
                    quick_stage = qc1.selectbox(
                        "Stage", PIPELINE_STAGES, index=PIPELINE_STAGES.index(profile.stage),
                        format_func=stage_group_label, key=f"quick_stage_{profile.id}",
                        label_visibility="collapsed",
                    )
                    if qc2.button(
                        "Move", key=f"quick_stage_move_{profile.id}", type="primary",
                        disabled=quick_stage == profile.stage,
                    ):
                        profile.stage = quick_stage
                        session.add(Activity(profile_id=profile.id, event=f"Stage changed to {quick_stage}",
                                              created_by_user_id=current_user["id"]))
                        session.commit()
                        flash(f"Moved to {quick_stage}.")
                        st.rerun()

            tab_overview, tab_docs, tab_tasks, tab_matches, tab_history = st.tabs(
                ["Overview", "Documents", "Tasks", "Matches", "History"]
            )

            with tab_overview:
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
                if profile.notes:
                    st.markdown(f"**Notes:** {profile.notes}")

                if can_write:
                    with st.expander("✏️ Edit profile"):
                        with st.form("edit_profile"):
                            st.caption("* required — everything else can be filled in later.")
                            c1, c2, c3 = st.columns(3)
                            full_name = c1.text_input("Full Name*", profile.full_name or "")
                            gender = c2.selectbox(
                                "Gender*", ["Bride", "Groom"], index=0 if profile.gender != "Groom" else 1
                            )
                            age = c3.number_input(
                                "Age", 18, 100, min(max(profile.age or 25, 18), 100),
                                disabled=profile.dob is not None,
                                help="Calculated from Date of Birth below." if profile.dob else None,
                            )

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
                            birth_time_val = c2.time_input(
                                "Birth Time", value=_parse_birth_time(profile.birth_time), step=300,
                            )
                            birth_place = c3.text_input("Birth Place", profile.birth_place or "")

                            c1, c2 = st.columns(2)
                            height_cm = c1.number_input(
                                "Height (cm)", 100.0, 250.0, min(max(profile.height_cm or 165.0, 100.0), 250.0)
                            )
                            food_preference = c2.selectbox(
                                "Food Preference", ["", "Vegetarian", "Non-Vegetarian", "Eggetarian"],
                                index=["", "Vegetarian", "Non-Vegetarian", "Eggetarian"].index(
                                    profile.food_preference or ""
                                ),
                            )

                            stage = st.selectbox(
                                "Status", PIPELINE_STAGES, index=PIPELINE_STAGES.index(profile.stage),
                                format_func=stage_group_label,
                            )
                            notes = st.text_area("Notes", profile.notes or "")

                            if st.form_submit_button("Save changes", type="primary"):
                                stage_changed = stage != profile.stage
                                profile.full_name = full_name or None
                                profile.gender = gender
                                profile.age = age_from_dob(dob) if dob else age
                                profile.religion = religion or None
                                profile.caste = caste or None
                                profile.gothram = gothram or None
                                profile.qualification = qualification or None
                                profile.occupation = occupation or None
                                profile.current_location = current_location or None
                                profile.dob = dob
                                profile.birth_time = birth_time_val.strftime("%H:%M") if birth_time_val else None
                                profile.birth_place = birth_place or None
                                profile.height_cm = height_cm
                                profile.food_preference = food_preference or None
                                profile.stage = stage
                                profile.notes = notes or None
                                if stage_changed:
                                    session.add(Activity(profile_id=profile.id, event=f"Stage changed to {stage}",
                                                          created_by_user_id=current_user["id"]))
                                session.commit()
                                flash("Saved.")
                                if birth_place and geo_lookup(birth_place) is None:
                                    flash(
                                        f"Saved, but '{birth_place}' wasn't found in the offline place database — "
                                        "astrology charts need an exact/nearby city name to compute. Try a larger "
                                        "nearby city.", kind="warning",
                                    )
                                st.rerun()

            with tab_docs:
                existing_docs = session.scalars(
                    select(Document).where(Document.profile_id == profile.id).order_by(Document.created_at.desc())
                ).all()
                if existing_docs:
                    for doc in existing_docs:
                        dcol1, dcol2, dcol3, dcol4 = st.columns([1, 2, 2, 1])
                        if doc.filename.lower().endswith(IMAGE_DOC_EXTENSIONS):
                            try:
                                dcol1.image(read_document(doc), width=60)
                            except FileNotFoundError:
                                dcol1.caption("—")
                        dcol2.markdown(f"**{doc.kind}** — {doc.filename}")
                        try:
                            file_bytes = read_document(doc)
                            dcol3.download_button("Download", file_bytes, file_name=doc.filename, key=f"dl_{doc.id}")
                        except FileNotFoundError:
                            dcol3.caption("File missing on disk")
                        if can_write and dcol4.button("Delete", key=f"del_doc_{doc.id}"):
                            delete_document(session, doc)
                            session.commit()
                            st.rerun()
                else:
                    st.caption("No documents uploaded yet — biodata, horoscope, and photos all go here.")

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
                                save_document(session, profile.id, doc_kind, doc_file.name, doc_file.read(),
                                              created_by_user_id=current_user["id"])
                                if doc_kind == "horoscope":
                                    profile.horoscope_available = True
                                session.add(Activity(profile_id=profile.id, event="Document Uploaded",
                                                      detail=f"{doc_kind}: {doc_file.name}",
                                                      created_by_user_id=current_user["id"]))
                                session.commit()
                                st.rerun()

            with tab_tasks:
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
                                                      detail=task.title, created_by_user_id=current_user["id"]))
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
                                session.add(Task(profile_id=profile.id, title=final_title, due_date=due,
                                                  created_by_user_id=current_user["id"]))
                                session.add(Activity(profile_id=profile.id, event="Task added", detail=final_title,
                                                      created_by_user_id=current_user["id"]))
                                session.commit()
                                st.rerun()

            with tab_matches:
                profile_matches = session.scalars(
                    select(MatchResult)
                    .where(or_(MatchResult.bride_id == profile.id, MatchResult.groom_id == profile.id))
                    .order_by(MatchResult.created_at.desc())
                ).all()
                if not profile_matches:
                    st.caption(
                        "No saved matches for this profile yet. Use **Matchmaking** to evaluate and "
                        "save a match against a candidate."
                    )
                else:
                    other_ids = {
                        (m.groom_id if m.bride_id == profile.id else m.bride_id) for m in profile_matches
                    }
                    other_profiles = {
                        p.id: p for p in session.scalars(select(Profile).where(Profile.id.in_(other_ids))).all()
                    }

                    def _match_option_label(mr: MatchResult) -> str:
                        other_id = mr.groom_id if mr.bride_id == profile.id else mr.bride_id
                        other = other_profiles.get(other_id)
                        other_name = other.full_name or "Unnamed" if other else "deleted profile"
                        score = f"{mr.koota_total:.1f}/36" if mr.koota_total is not None else f"{mr.practical_score or 0:.0f}%"
                        return f"#{other_id} {other_name} — {score} — {mr.created_at:%d %b %Y}"

                    match_options = {mr.id: _match_option_label(mr) for mr in profile_matches}
                    picked_match_id = st.selectbox(
                        f"{len(profile_matches)} saved match(es) — pick one to view",
                        options=list(match_options.keys()),
                        format_func=lambda mid: match_options[mid],
                        key=f"profile_match_pick_{profile.id}",
                    )
                    picked_match = next(m for m in profile_matches if m.id == picked_match_id)
                    other_id = picked_match.groom_id if picked_match.bride_id == profile.id else picked_match.bride_id
                    bride = profile if picked_match.bride_id == profile.id else other_profiles.get(other_id)
                    groom = profile if picked_match.groom_id == profile.id else other_profiles.get(other_id)
                    st.divider()
                    render_saved_match_result(picked_match, bride, groom)

            with tab_history:
                theme.section("Activity Timeline")
                activities = session.scalars(
                    select(Activity).where(Activity.profile_id == profile.id).order_by(Activity.created_at.desc())
                ).all()
                actor_ids = {a.created_by_user_id for a in activities if a.created_by_user_id}
                actor_names = {
                    u.id: (u.full_name or u.username)
                    for u in session.scalars(select(User).where(User.id.in_(actor_ids))).all()
                } if actor_ids else {}
                for a in activities:
                    who = f" by {actor_names[a.created_by_user_id]}" if a.created_by_user_id in actor_names else ""
                    st.markdown(
                        f"**{a.created_at:%d %b %Y, %H:%M}** — {a.event}{who}" + (f": {a.detail}" if a.detail else "")
                    )

                if can_write:
                    with st.form("add_activity"):
                        event = st.text_input("Log new activity (e.g. 'Parents Contacted', 'Meeting Scheduled')")
                        detail = st.text_input("Detail (optional)")
                        if st.form_submit_button("Log activity"):
                            if event:
                                session.add(Activity(profile_id=profile.id, event=event, detail=detail or None,
                                                      created_by_user_id=current_user["id"]))
                                session.commit()
                                st.rerun()

                if can_write:
                    st.divider()
                    with st.expander("🗑️ Delete this profile"):
                        st.warning(
                            "Permanently deletes this profile along with its documents, tasks, "
                            "activity history, and any saved match results. This cannot be undone."
                        )
                        confirm_key = f"confirm_delete_profile_{profile.id}"
                        if confirm_key in st.session_state:
                            st.error(f"Really delete profile #{profile.id} — {profile.full_name or 'Unnamed'}?")
                            with st.container(horizontal=True):
                                if st.button("Yes, delete permanently", key=f"confirm_delete_profile_btn_{profile.id}", type="primary"):
                                    summary = delete_profile(session, profile)
                                    del st.session_state[confirm_key]
                                    st.session_state["_clear_profiles_selection"] = True
                                    flash(f"Deleted profile #{summary['id']}.")
                                    st.rerun()
                                if st.button("Cancel", key=f"cancel_delete_profile_{profile.id}"):
                                    del st.session_state[confirm_key]
                                    st.rerun()
                        else:
                            if st.button("Delete this profile", key=f"delete_profile_{profile.id}"):
                                st.session_state[confirm_key] = True
                                st.rerun()
    else:
        st.info("No profiles match these filters.")

with tab_manual:
    if not can_write:
        st.info("Your account has read-only (Viewer) access.")
    else:
        with st.form("add_manual_profile"):
            st.caption("* required — everything else can be filled in later.")
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
                    full_name=full_name, gender=gender,
                    age=age_from_dob(dob_input) if dob_input else age,
                    phone=phone or None,
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

            with st.container(horizontal=True):
                if st.button("Create profile" + (" anyway" if duplicates else ""), type="primary"):
                    with get_session() as session:
                        profile = Profile(stage="New", **pending)
                        session.add(profile)
                        session.flush()
                        session.add(Activity(profile_id=profile.id, event="Profile Created", detail="Manual entry",
                                              created_by_user_id=current_user["id"]))
                        session.commit()
                        new_id = profile.id
                    del st.session_state["pending_manual_profile"]
                    st.success(f"Created profile #{new_id}.")
                if st.button("Cancel"):
                    del st.session_state["pending_manual_profile"]
                    st.rerun()

with tab_duplicates:
    st.caption(
        "Pairwise scan of every profile for likely duplicates (same gender, "
        "matching phone/DOB/similar name) — for profiles that already exist, "
        "not the message-level check shown while extracting a new one."
    )
    with get_session() as session:
        pairs = find_all_duplicate_pairs(session)

    if not pairs:
        st.info("No likely duplicate profiles found.")
    else:
        st.caption(f"{len(pairs)} possible duplicate pair(s), highest match first.")
        for pair in pairs:
            a, b = pair.profile_a, pair.profile_b
            label = (
                f"#{a.id} {a.full_name or 'Unnamed'} ↔ #{b.id} {b.full_name or 'Unnamed'} "
                f"— {pair.score}% match"
            )
            with st.expander(label):
                st.markdown("; ".join(pair.reasons))
                c1, c2 = st.columns(2)
                c1.markdown(f"**#{a.id} {a.full_name or 'Unnamed'}**")
                c1.caption(f"Created {a.created_at:%d %b %Y} · Stage: {a.stage}")
                c2.markdown(f"**#{b.id} {b.full_name or 'Unnamed'}**")
                c2.caption(f"Created {b.created_at:%d %b %Y} · Stage: {b.stage}")

                if can_write:
                    with st.container(horizontal=True):
                        if st.button(f"Merge #{b.id} into #{a.id} (keep #{a.id})", key=f"merge_pair_{a.id}_{b.id}_a"):
                            with get_session() as session:
                                keep = session.get(Profile, a.id)
                                remove = session.get(Profile, b.id)
                                summary = merge_profiles(session, keep=keep, remove=remove,
                                                          created_by_user_id=current_user["id"])
                            # a profile just vanished from the Search & Manage table (rendered
                            # regardless of which tab is active) — clear its selection so a
                            # stale row index can't be indexed out of range on the rerun below
                            st.session_state["_clear_profiles_selection"] = True
                            flash(
                                f"Merged #{b.id} into #{a.id}: filled {len(summary['filled'])} field(s), "
                                f"moved {summary['documents']} document(s), {summary['tasks']} task(s), "
                                f"{summary['matches']} match result(s)."
                            )
                            st.rerun()
                        if st.button(f"Merge #{a.id} into #{b.id} (keep #{b.id})", key=f"merge_pair_{a.id}_{b.id}_b"):
                            with get_session() as session:
                                keep = session.get(Profile, b.id)
                                remove = session.get(Profile, a.id)
                                summary = merge_profiles(session, keep=keep, remove=remove,
                                                          created_by_user_id=current_user["id"])
                            st.session_state["_clear_profiles_selection"] = True
                            flash(
                                f"Merged #{a.id} into #{b.id}: filled {len(summary['filled'])} field(s), "
                                f"moved {summary['documents']} document(s), {summary['tasks']} task(s), "
                                f"{summary['matches']} match result(s)."
                            )
                            st.rerun()
