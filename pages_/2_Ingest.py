from collections import Counter
from datetime import date

import streamlit as st
from sqlalchemy import select

from soulmatch import auth, config
from soulmatch.db import get_session
from soulmatch.duplicates import find_duplicate_candidates, merge_into_profile
from soulmatch.extraction.extractor import extract_profile, is_likely_profile
from soulmatch.extraction.llm import LLMError
from soulmatch.ingest.whatsapp_export import parse_export
from soulmatch.models import Activity, Profile, RawMessage
from soulmatch.ui import flash, show_flash

current_user = auth.require_login()
st.title("📥 Import Messages — WhatsApp Chat Export")
show_flash()

if not auth.can_edit(current_user["role"]):
    st.info("Your account has read-only (Viewer) access. Sign in with an editor role to import messages.")
    st.stop()

tab_import, tab_review, tab_history = st.tabs(["📥 Import", "📋 Review queue", "🗂️ History"])

with tab_import:
    st.markdown(
        """
1. In WhatsApp, open the group/chat → ⋮ menu → **More** → **Export chat** → **Without Media** (or with media if you want photos too).
2. Upload the resulting `.txt` or `.zip` file below.
"""
    )

    with st.expander("Or paste / manually enter a single message"):
        manual_text = st.text_area("Message text", height=150)
        manual_sender = st.text_input("Sender name (optional)")
        if st.button("Add as raw message"):
            if manual_text.strip():
                content = manual_text.strip()
                sender = manual_sender or None
                with get_session() as session:
                    exists = session.scalar(
                        select(RawMessage).where(RawMessage.sender == sender, RawMessage.content == content)
                    )
                    if exists:
                        st.warning("An identical message already exists — not added again.")
                    else:
                        session.add(RawMessage(source="manual", sender=sender, content=content))
                        session.commit()
                        st.success("Message added. Switch to Review queue to process it.")
            else:
                st.warning("Enter some text first.")

    uploaded = st.file_uploader("WhatsApp export (.txt or .zip)", type=["txt", "zip"])

    if uploaded is not None:
        data = uploaded.read()
        try:
            messages, media = parse_export(data, uploaded.name)
        except Exception as e:  # noqa: BLE001 — surface parser errors to the user
            st.error(f"Could not parse file: {e}")
            messages, media = [], {}

        if messages:
            st.success(f"Parsed {len(messages)} messages" + (f", {len(media)} media files" if media else ""))
            likely = sum(1 for m in messages if is_likely_profile(m.content))
            st.caption(f"{likely} message(s) look like matrimonial profiles based on keyword pre-filter.")

            if st.button(f"Import {len(messages)} messages into database", type="primary"):
                with get_session() as session:
                    existing_pairs = {
                        tuple(row) for row in session.execute(select(RawMessage.sender, RawMessage.content)).all()
                    }
                    new_count = skipped_count = 0
                    for m in messages:
                        pair = (m.sender, m.content)
                        if pair in existing_pairs:
                            skipped_count += 1
                            continue
                        session.add(RawMessage(
                            source="whatsapp_export",
                            chat_name=uploaded.name,
                            sender=m.sender,
                            sent_at=m.sent_at,
                            content=m.content,
                            media_filename=m.media_filename,
                            is_system=m.is_system,
                        ))
                        existing_pairs.add(pair)
                        new_count += 1
                    session.commit()
                flash(
                    f"Imported {new_count} message(s)."
                    + (f" Skipped {skipped_count} already in database." if skipped_count else "")
                )
                st.rerun()

with tab_review:
    st.subheader("Unprocessed Messages")

    with get_session() as session:
        unprocessed = session.scalars(
            select(RawMessage).where(RawMessage.processed.is_(False)).order_by(RawMessage.created_at.desc())
        ).all()

    st.caption(f"{len(unprocessed)} unprocessed message(s) total. AI service: **{config.LLM_PROVIDER}**")
    if config.LLM_PROVIDER == "mock":
        st.warning(
            "⚠️ Offline extraction mode — most fields will come back empty. "
            "Add a GEMINI_API_KEY or ANTHROPIC_API_KEY in .env and restart the app to enable real AI extraction."
        )

    if not unprocessed:
        st.info("Nothing to process. Import messages in the Import tab.")
    else:
        only_likely = st.checkbox("Only show messages that look like profiles", value=True)
        filtered = [m for m in unprocessed if not only_likely or is_likely_profile(m.content)]
        shown = filtered[:30]

        if len(shown) != len(unprocessed):
            reasons = []
            if only_likely and len(filtered) != len(unprocessed):
                reasons.append("profile-like filter on")
            if len(filtered) > 30:
                reasons.append("showing first 30")
            st.caption(
                f"Showing {len(shown)} of {len(unprocessed)}" + (f" — {', '.join(reasons)}" if reasons else ".")
            )

        if shown and st.button(f"⚡ Auto-process all {len(shown)} shown message(s)", key="bulk_autoprocess"):
            saved = skipped_low_conf = skipped_dup = errors = 0
            progress = st.progress(0.0, text="Starting…")
            with get_session() as session:
                for i, msg in enumerate(shown, start=1):
                    progress.progress(i / len(shown), text=f"Processing {i} of {len(shown)} — extracting…")
                    raw = session.get(RawMessage, msg.id)
                    if raw is None or raw.processed:
                        continue
                    try:
                        data = extract_profile(raw.content)
                    except LLMError:
                        errors += 1
                        continue
                    confidence = data.pop("confidence", 0)
                    if not confidence or confidence < 0.3:
                        skipped_low_conf += 1
                        continue
                    dup_dob = data.get("dob") if isinstance(data.get("dob"), date) else None
                    duplicates = find_duplicate_candidates(
                        session,
                        full_name=data.get("full_name"),
                        gender=data.get("gender"),
                        phone=data.get("phone"),
                        whatsapp=data.get("whatsapp"),
                        dob=dup_dob,
                    )
                    if duplicates:
                        skipped_dup += 1
                        continue
                    profile = Profile(
                        **{k: v for k, v in data.items() if k in Profile.__table__.columns.keys()},
                        stage="AI Extracted",
                        source_message_id=raw.id,
                    )
                    session.add(profile)
                    session.flush()
                    session.add(Activity(profile_id=profile.id, event="Profile Created",
                                          detail=f"Auto-extracted via {config.LLM_PROVIDER}",
                                          created_by_user_id=current_user["id"]))
                    raw.processed = True
                    saved += 1
                session.commit()
            progress.empty()
            flash(f"Auto-processed: {saved} profile(s) created.")
            if skipped_low_conf:
                flash(
                    f"{skipped_low_conf} message(s) skipped — low confidence, left for manual review.",
                    kind="warning",
                )
            if skipped_dup:
                flash(
                    f"{skipped_dup} message(s) skipped — possible duplicate(s) found, left for manual review.",
                    kind="warning",
                )
            if errors:
                flash(f"{errors} message(s) failed extraction (LLM error) and were left unprocessed.", kind="error")
            st.rerun()

        content_counts = Counter(m.content for m in shown)
        dupe_contents = {c for c, n in content_counts.items() if n > 1}
        if dupe_contents:
            seen_contents = set()
            dupe_ids = []
            for m in shown:  # already newest-first, so this keeps the newest of each
                if m.content in dupe_contents:
                    if m.content in seen_contents:
                        dupe_ids.append(m.id)
                    else:
                        seen_contents.add(m.content)
            if st.button(
                f"🗑️ Delete {len(dupe_ids)} exact-duplicate message(s), keep the newest of each",
                key="bulk_dedupe",
            ):
                with get_session() as session:
                    for mid in dupe_ids:
                        raw = session.get(RawMessage, mid)
                        if raw:
                            session.delete(raw)
                    session.commit()
                flash(f"Deleted {len(dupe_ids)} duplicate message(s).")
                st.rerun()

        for msg in shown:
            pending_key = f"pending_extract_{msg.id}"
            confirm_delete_key = f"confirm_delete_{msg.id}"
            with st.expander(f"{msg.sender or 'Unknown'} — {msg.content[:80]}"):
                st.text(msg.content)

                if confirm_delete_key in st.session_state:
                    st.warning("Delete this message permanently? This cannot be undone.")
                    with st.container(horizontal=True):
                        if st.button("Yes, delete", key=f"confirm_delete_btn_{msg.id}", type="primary"):
                            with get_session() as session:
                                raw = session.get(RawMessage, msg.id)
                                if raw:
                                    session.delete(raw)
                                session.commit()
                            del st.session_state[confirm_delete_key]
                            flash("Deleted.")
                            st.rerun()
                        if st.button("Cancel", key=f"cancel_delete_{msg.id}"):
                            del st.session_state[confirm_delete_key]
                            st.rerun()
                elif pending_key not in st.session_state:
                    with st.container(horizontal=True):
                        if st.button("Extract profile", key=f"extract_{msg.id}"):
                            try:
                                data = extract_profile(msg.content)
                            except LLMError as e:
                                st.error(str(e))
                            else:
                                confidence = data.pop("confidence", 0)
                                if confidence and confidence >= 0.3:
                                    st.session_state[pending_key] = data
                                    st.rerun()
                                else:
                                    st.warning(f"Low confidence ({confidence:.0%}) this is a profile — not saved.")
                        if st.button(
                            "Not a profile → archive", key=f"skip_{msg.id}",
                            help="Marks this message as reviewed without creating a profile. "
                                 "It moves to History and can be reloaded later if you change your mind.",
                        ):
                            with get_session() as session:
                                raw = session.get(RawMessage, msg.id)
                                raw.processed = True
                                session.commit()
                            st.rerun()
                        if st.button(
                            "🗑️ Delete permanently", key=f"delete_{msg.id}",
                            help="Permanently removes this message from the database. This cannot be undone.",
                        ):
                            st.session_state[confirm_delete_key] = True
                            st.rerun()
                else:
                    data = st.session_state[pending_key]
                    st.write("**Extracted fields:**", {k: v for k, v in data.items() if v is not None})

                    with get_session() as session:
                        dup_dob = data.get("dob") if isinstance(data.get("dob"), date) else None
                        duplicates = find_duplicate_candidates(
                            session,
                            full_name=data.get("full_name"),
                            gender=data.get("gender"),
                            phone=data.get("phone"),
                            whatsapp=data.get("whatsapp"),
                            dob=dup_dob,
                        )
                        if duplicates:
                            st.warning(f"⚠️ {len(duplicates)} possible duplicate(s) found:")
                            for d in duplicates[:5]:
                                dc1, dc2 = st.columns([4, 1])
                                dc1.markdown(
                                    f"- **#{d.profile.id} {d.profile.full_name or 'Unnamed'}** "
                                    f"({d.score}% match) — {'; '.join(d.reasons)}"
                                )
                                if dc2.button(f"Merge into #{d.profile.id}", key=f"merge_{msg.id}_{d.profile.id}"):
                                    with get_session() as merge_session:
                                        target = merge_session.get(Profile, d.profile.id)
                                        filled = merge_into_profile(target, data)
                                        merge_session.add(Activity(
                                            profile_id=target.id, event="Profile Merged",
                                            detail=f"Merged from message #{msg.id} via {config.LLM_PROVIDER}: "
                                                   + (f"filled {', '.join(filled)}" if filled else "no new fields"),
                                            created_by_user_id=current_user["id"],
                                        ))
                                        raw = merge_session.get(RawMessage, msg.id)
                                        raw.processed = True
                                        merge_session.commit()
                                    del st.session_state[pending_key]
                                    flash(f"Merged into profile #{d.profile.id} — {len(filled)} field(s) filled in.")
                                    st.rerun()

                    with st.container(horizontal=True):
                        save_label = "Save as new profile anyway" if duplicates else "Save profile"
                        if st.button(save_label, key=f"save_{msg.id}", type="primary"):
                            with get_session() as session:
                                profile = Profile(
                                    **{k: v for k, v in data.items() if k in Profile.__table__.columns.keys()},
                                    stage="AI Extracted",
                                    source_message_id=msg.id,
                                )
                                session.add(profile)
                                session.flush()
                                session.add(Activity(profile_id=profile.id, event="Profile Created",
                                                      detail=f"Extracted via {config.LLM_PROVIDER}",
                                                      created_by_user_id=current_user["id"]))
                                raw = session.get(RawMessage, msg.id)
                                raw.processed = True
                                session.commit()
                            del st.session_state[pending_key]
                            flash("Profile created.")
                            st.rerun()
                        if st.button(
                            "Start over", key=f"discard_{msg.id}",
                            help="Drops this extraction attempt; the message stays in the queue so you can try again.",
                        ):
                            del st.session_state[pending_key]
                            st.rerun()

with tab_history:
    with get_session() as session:
        processed_msgs = session.scalars(
            select(RawMessage).where(RawMessage.processed.is_(True)).order_by(RawMessage.created_at.desc())
        ).all()[:30]
        profiles_by_msg = {
            p.source_message_id: p
            for p in session.scalars(select(Profile).where(Profile.source_message_id.isnot(None))).all()
        }

    if not processed_msgs:
        st.caption("Nothing processed yet.")
    else:
        st.caption(
            f"Showing {len(processed_msgs)} most recently processed message(s). "
            "Reload one — e.g. it was extracted offline before a real AI service was set up — "
            "to send it back to the Review queue for re-extraction."
        )
        if st.button(f"Reload all {len(processed_msgs)} shown message(s) for reprocessing", key="bulk_reload"):
            with get_session() as session:
                for m in processed_msgs:
                    raw = session.get(RawMessage, m.id)
                    raw.processed = False
                session.commit()
            flash("Reloaded — check the Review queue tab.")
            st.rerun()

        for msg in processed_msgs:
            profile = profiles_by_msg.get(msg.id)
            confirm_delete_key = f"confirm_delete_proc_{msg.id}"
            with st.expander(f"{msg.sender or 'Unknown'} — {msg.content[:80]}"):
                st.text(msg.content)
                if profile:
                    st.caption(f"Linked to profile #{profile.id} — {profile.full_name or 'Unnamed'}")
                else:
                    st.caption("No profile was created from this message (archived as not a profile).")

                if confirm_delete_key in st.session_state:
                    st.warning("Delete this message permanently? This cannot be undone.")
                    with st.container(horizontal=True):
                        if st.button("Yes, delete", key=f"confirm_delete_proc_btn_{msg.id}", type="primary"):
                            with get_session() as session:
                                raw = session.get(RawMessage, msg.id)
                                if raw:
                                    session.delete(raw)
                                session.commit()
                            del st.session_state[confirm_delete_key]
                            flash("Deleted.")
                            st.rerun()
                        if st.button("Cancel", key=f"cancel_delete_proc_{msg.id}"):
                            del st.session_state[confirm_delete_key]
                            st.rerun()
                else:
                    with st.container(horizontal=True):
                        if st.button("Reload for reprocessing", key=f"reload_{msg.id}"):
                            with get_session() as session:
                                raw = session.get(RawMessage, msg.id)
                                raw.processed = False
                                session.commit()
                            flash("Reloaded — check the Review queue tab.")
                            st.rerun()
                        if profile:
                            st.caption("Delete the profile first to remove this message.")
                        elif st.button(
                            "🗑️ Delete permanently", key=f"delete_proc_{msg.id}",
                            help="Permanently removes this message from the database. This cannot be undone.",
                        ):
                            st.session_state[confirm_delete_key] = True
                            st.rerun()
