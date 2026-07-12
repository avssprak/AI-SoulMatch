from collections import Counter
from datetime import date

import streamlit as st
from sqlalchemy import select

from soulmatch import auth, billing, config
from soulmatch.db import get_session
from soulmatch.duplicates import find_duplicate_candidates, merge_into_profile

# A duplicate score at or above this is treated as certainly the same person
# (e.g. matching phone number scores 60 on its own) and gets auto-merged into
# the existing profile during bulk processing instead of being left for
# manual review — re-sent/updated biodata for someone already in the system
# should update their record, not sit in a queue.
AUTO_MERGE_SCORE_THRESHOLD = 60
from soulmatch.extraction.extractor import extract_profile, is_likely_profile
from soulmatch.extraction.llm import LLMError
from soulmatch.ingest.document_import import parse_document
from soulmatch.ingest.whatsapp_export import parse_export
from soulmatch.models import Activity, Profile, RawMessage
from soulmatch import theme
from soulmatch.tenancy import get_owned, owned, owner_id_of
from soulmatch.ui import check_upload_size, flash, show_flash


def _metered_extract(session, current_user: dict, text: str) -> dict:
    """extract_profile(), quota-checked and usage-recorded for real providers.
    Mock provider is free/offline — no quota check, no AiUsage row (V3-2-1).
    Raises billing.QuotaExceeded or LLMError; caller handles both."""
    if config.LLM_PROVIDER == "mock":
        return extract_profile(text)
    billing.require_quota(session, current_user)
    usage = {"tokens_in": 0, "tokens_out": 0}
    data = extract_profile(text, usage_out=usage)
    billing.record_usage(session, current_user["id"], "extract", usage["tokens_in"], usage["tokens_out"])
    return data


def _auto_process_raw_messages(message_ids: list[int], current_user: dict) -> None:
    """Run extraction + duplicate-check + save/merge over the given raw
    message ids, then flash a summary and rerun. Shared by the Review
    queue's manual "Auto-process" button and the Import tab's "process
    immediately after import" checkbox — one implementation of the
    extraction loop, not two copies that drift apart."""
    if not message_ids:
        return
    saved = merged = skipped_low_conf = skipped_dup = errors = 0
    skipped_quota = skipped_cap = 0
    quota_exhausted = cap_reached = False
    owner = owner_id_of(current_user)
    progress = st.progress(0.0, text="Starting…")
    with get_session() as session:
        for i, mid in enumerate(message_ids, start=1):
            progress.progress(i / len(message_ids), text=f"Processing {i} of {len(message_ids)} — extracting…")
            raw = get_owned(session, RawMessage, mid, owner)
            if raw is None or raw.processed:
                continue
            if quota_exhausted:
                skipped_quota += 1
                continue
            if cap_reached:
                skipped_cap += 1
                continue
            try:
                data = _metered_extract(session, current_user, raw.content)
            except billing.QuotaExceeded:
                quota_exhausted = True
                skipped_quota += 1
                continue
            except LLMError as e:
                raw.error = str(e)
                errors += 1
                continue
            raw.error = None
            confidence = data.pop("confidence", 0)
            if not confidence or confidence < 0.3:
                skipped_low_conf += 1
                continue
            dup_dob = data.get("dob") if isinstance(data.get("dob"), date) else None
            duplicates = find_duplicate_candidates(
                session,
                owner,
                full_name=data.get("full_name"),
                gender=data.get("gender"),
                phone=data.get("phone"),
                whatsapp=data.get("whatsapp"),
                dob=dup_dob,
            )
            top = duplicates[0] if duplicates else None
            if top and top.score >= AUTO_MERGE_SCORE_THRESHOLD:
                target = top.profile
                filled = merge_into_profile(target, data)
                session.add(Activity(
                    profile_id=target.id, owner_user_id=owner, event="Profile Merged",
                    detail=f"Auto-merged from message #{raw.id} via {config.LLM_PROVIDER} "
                           f"({top.score}% match — {'; '.join(top.reasons)}): "
                           + (f"filled {', '.join(filled)}" if filled else "no new fields"),
                    created_by_user_id=current_user["id"],
                ))
                raw.processed = True
                merged += 1
                continue
            if top:
                skipped_dup += 1
                continue
            can_add, cap_message = billing.can_add_profile(session, current_user)
            if not can_add:
                cap_reached = True
                skipped_cap += 1
                continue
            profile = Profile(
                **{k: v for k, v in data.items() if k in Profile.__table__.columns.keys()},
                stage="AI Extracted",
                source_message_id=raw.id,
                owner_user_id=owner,
            )
            session.add(profile)
            session.flush()
            session.add(Activity(profile_id=profile.id, owner_user_id=owner, event="Profile Created",
                                  detail=f"Auto-extracted via {config.LLM_PROVIDER}",
                                  created_by_user_id=current_user["id"]))
            raw.processed = True
            saved += 1
        session.commit()
    progress.empty()
    flash(f"Auto-processed: {saved} profile(s) created" + (f", {merged} merged into existing profiles." if merged else "."))
    if skipped_low_conf:
        flash(
            f"{skipped_low_conf} message(s) skipped — low confidence, left for manual review.",
            kind="warning",
        )
    if skipped_dup:
        flash(
            f"{skipped_dup} message(s) skipped — possible duplicate(s) found (below auto-merge confidence), "
            "left for manual review.",
            kind="warning",
        )
    if skipped_quota:
        flash(
            f"{skipped_quota} message(s) skipped — AI action quota reached this month. "
            "Upgrade on My Plan or wait for next month's reset.",
            kind="warning",
        )
    if skipped_cap:
        flash(
            f"{skipped_cap} message(s) skipped — profile limit reached for your plan. "
            "Upgrade on My Plan for unlimited profiles.",
            kind="warning",
        )
    if errors:
        flash(f"{errors} message(s) failed extraction (LLM error) and were left unprocessed.", kind="error")


current_user = auth.require_login()
owner = owner_id_of(current_user)
theme.page_header("Import Profiles", "Bring in WhatsApp chat exports and documents — AI turns them into structured profiles.")
show_flash()

with get_session() as _session:
    _review_count = len(_session.scalars(
        owned(select(RawMessage).where(RawMessage.processed.is_(False)), RawMessage, owner)
    ).all())
    _history_count = len(_session.scalars(
        owned(select(RawMessage).where(RawMessage.processed.is_(True)), RawMessage, owner)
    ).all())

tab_import, tab_review, tab_history = st.tabs(
    ["📥 Import", f"📋 Review queue ({_review_count})", f"🗂️ History ({_history_count})"]
)

with tab_import:
    st.markdown(
        """
1. In WhatsApp, open the group/chat → ⋮ menu → **More** → **Export chat** → **Without Media** (or with media if you want photos too).
2. Upload the resulting `.txt` or `.zip` file below — or any other document (a biodata list, forwarded PDF, plain text).
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
                        owned(select(RawMessage).where(RawMessage.sender == sender, RawMessage.content == content),
                              RawMessage, owner)
                    )
                    if exists:
                        st.warning("An identical message already exists — not added again.")
                    else:
                        session.add(RawMessage(source="manual", sender=sender, content=content, owner_user_id=owner))
                        session.commit()
                        st.success("Message added. Switch to Review queue to process it.")
            else:
                st.warning("Enter some text first.")

    uploaded = st.file_uploader(
        "Upload a file — WhatsApp export (.txt/.zip) or any other document (.txt/.pdf)",
        type=["txt", "zip", "pdf"],
    )

    if uploaded is not None and check_upload_size(uploaded):
        data = uploaded.read()
        is_pdf = uploaded.name.lower().endswith(".pdf")
        messages, media = [], {}
        chunks: list[str] = []
        parsed_as = None

        if not is_pdf:
            # Try the WhatsApp export parser first — it's the primary use case and
            # a plain .txt document has no export-format lines to falsely match.
            try:
                messages, media = parse_export(data, uploaded.name)
            except Exception as e:  # noqa: BLE001 — surface parser errors to the user
                st.error(f"Could not parse file: {e}")
                messages, media = [], {}
            if messages:
                parsed_as = "whatsapp_export"

        if parsed_as is None and not uploaded.name.lower().endswith(".zip"):
            # .pdf, or a .txt that didn't look like a WhatsApp export — fall back
            # to the generic document splitter. parse_document only understands
            # .txt/.pdf, so a non-export .zip has no fallback (same as before).
            try:
                chunks = parse_document(data, uploaded.name)
            except Exception as e:  # noqa: BLE001 — surface parser errors to the user
                st.error(f"Could not read file: {e}")
                chunks = []
            if chunks:
                parsed_as = "document"

        if parsed_as is None:
            st.warning(
                "No messages or text could be extracted from this file. "
                "If this is a plain list of profiles, paste each one individually using "
                "'Or paste / manually enter a single message' above."
            )

        elif parsed_as == "whatsapp_export":
            st.success(f"Parsed as a WhatsApp export — {len(messages)} messages"
                       + (f", {len(media)} media files" if media else ""))
            likely = sum(1 for m in messages if is_likely_profile(m.content))
            st.caption(f"{likely} message(s) look like matrimonial profiles based on keyword pre-filter.")
            auto_process = st.checkbox(
                "Extract profiles immediately after import", key="auto_process_wa",
                help="Runs the same extraction as 'Auto-process' in Review queue, right after import.",
            )

            if st.button(f"Import {len(messages)} messages into database", type="primary"):
                with get_session() as session:
                    existing_pairs = {
                        tuple(row) for row in session.execute(
                            select(RawMessage.sender, RawMessage.content).where(RawMessage.owner_user_id == owner)
                        ).all()
                    }
                    new_ids, new_count, skipped_count = [], 0, 0
                    for m in messages:
                        pair = (m.sender, m.content)
                        if pair in existing_pairs:
                            skipped_count += 1
                            continue
                        raw = RawMessage(
                            source="whatsapp_export",
                            owner_user_id=owner,
                            chat_name=uploaded.name,
                            sender=m.sender,
                            sent_at=m.sent_at,
                            content=m.content,
                            media_filename=m.media_filename,
                            is_system=m.is_system,
                        )
                        session.add(raw)
                        session.flush()
                        new_ids.append(raw.id)
                        existing_pairs.add(pair)
                        new_count += 1
                    session.commit()
                flash(
                    f"Imported {new_count} message(s)."
                    + (f" Skipped {skipped_count} already in database." if skipped_count else "")
                )
                if auto_process and new_ids:
                    with get_session() as session:
                        likely_ids = [
                            mid for mid in new_ids
                            if is_likely_profile(get_owned(session, RawMessage, mid, owner).content)
                        ]
                    _auto_process_raw_messages(likely_ids, current_user)
                st.rerun()

        elif parsed_as == "document":
            likely = sum(1 for c in chunks if is_likely_profile(c))
            st.success(f"Parsed as a document — split into {len(chunks)} block(s) of text, "
                       f"{likely} look like matrimonial profiles.")
            auto_process_doc = st.checkbox(
                "Extract profiles immediately after import", key="auto_process_doc",
                help="Runs the same extraction as 'Auto-process' in Review queue, right after import.",
            )

            if st.button(f"Import {len(chunks)} block(s) into database", type="primary", key="import_doc_blocks"):
                with get_session() as session:
                    existing = {row[0] for row in session.execute(
                        select(RawMessage.content).where(RawMessage.owner_user_id == owner)
                    ).all()}
                    new_ids, new_count, skipped_count = [], 0, 0
                    for chunk in chunks:
                        if chunk in existing:
                            skipped_count += 1
                            continue
                        raw = RawMessage(source="document", chat_name=uploaded.name, content=chunk, owner_user_id=owner)
                        session.add(raw)
                        session.flush()
                        new_ids.append(raw.id)
                        existing.add(chunk)
                        new_count += 1
                    session.commit()
                flash(
                    f"Imported {new_count} block(s)."
                    + (f" Skipped {skipped_count} already in database." if skipped_count else "")
                )
                if auto_process_doc and new_ids:
                    with get_session() as session:
                        likely_ids = [
                            mid for mid in new_ids
                            if is_likely_profile(get_owned(session, RawMessage, mid, owner).content)
                        ]
                    _auto_process_raw_messages(likely_ids, current_user)
                st.rerun()

with tab_review:
    theme.section("Unprocessed Messages")

    with get_session() as session:
        unprocessed = session.scalars(
            owned(select(RawMessage).where(RawMessage.processed.is_(False)), RawMessage, owner)
            .order_by(RawMessage.created_at.desc())
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
        failed_count = sum(1 for m in unprocessed if m.error)
        col1, col2 = st.columns(2)
        only_likely = col1.checkbox("Only show messages that look like profiles", value=True)
        only_failed = col2.checkbox(f"Only show failed extractions ({failed_count})", value=False)
        filtered = [
            m for m in unprocessed
            if (not only_likely or is_likely_profile(m.content)) and (not only_failed or m.error)
        ]
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
            _auto_process_raw_messages([m.id for m in shown], current_user)
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
                        raw = get_owned(session, RawMessage, mid, owner)
                        if raw:
                            session.delete(raw)
                    session.commit()
                flash(f"Deleted {len(dupe_ids)} duplicate message(s).")
                st.rerun()

        for msg in shown:
            pending_key = f"pending_extract_{msg.id}"
            confirm_delete_key = f"confirm_delete_{msg.id}"
            title = f"{msg.sender or 'Unknown'} — {msg.content[:80]}"
            if msg.error:
                title = f"⚠️ {title}"
            with st.expander(title):
                st.text(msg.content)
                if msg.error:
                    st.error(f"Last extraction failed: {msg.error}")

                if confirm_delete_key in st.session_state:
                    st.warning("Delete this message permanently? This cannot be undone.")
                    with st.container(horizontal=True):
                        if st.button("Yes, delete", key=f"confirm_delete_btn_{msg.id}", type="primary"):
                            with get_session() as session:
                                raw = get_owned(session, RawMessage, msg.id, owner)
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
                        if st.button(
                            "🔁 Retry extraction" if msg.error else "Extract profile", key=f"extract_{msg.id}",
                        ):
                            try:
                                with get_session() as session:
                                    data = _metered_extract(session, current_user, msg.content)
                                    session.commit()
                            except billing.QuotaExceeded as e:
                                st.warning(str(e))
                            except LLMError as e:
                                with get_session() as session:
                                    raw = get_owned(session, RawMessage, msg.id, owner)
                                    raw.error = str(e)
                                    session.commit()
                                st.error(str(e))
                            else:
                                with get_session() as session:
                                    raw = get_owned(session, RawMessage, msg.id, owner)
                                    raw.error = None
                                    session.commit()
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
                                raw = get_owned(session, RawMessage, msg.id, owner)
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
                            owner,
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
                                        target = get_owned(merge_session, Profile, d.profile.id, owner)
                                        filled = merge_into_profile(target, data)
                                        merge_session.add(Activity(
                                            profile_id=target.id, owner_user_id=owner, event="Profile Merged",
                                            detail=f"Merged from message #{msg.id} via {config.LLM_PROVIDER}: "
                                                   + (f"filled {', '.join(filled)}" if filled else "no new fields"),
                                            created_by_user_id=current_user["id"],
                                        ))
                                        raw = get_owned(merge_session, RawMessage, msg.id, owner)
                                        raw.processed = True
                                        merge_session.commit()
                                    del st.session_state[pending_key]
                                    flash(f"Merged into profile #{d.profile.id} — {len(filled)} field(s) filled in.")
                                    st.rerun()

                    with st.container(horizontal=True):
                        save_label = "Save as new profile anyway" if duplicates else "Save profile"
                        if st.button(save_label, key=f"save_{msg.id}", type="primary"):
                            with get_session() as session:
                                can_add, cap_message = billing.can_add_profile(session, current_user)
                                if not can_add:
                                    st.warning(cap_message)
                                else:
                                    profile = Profile(
                                        **{k: v for k, v in data.items() if k in Profile.__table__.columns.keys()},
                                        stage="AI Extracted",
                                        source_message_id=msg.id,
                                        owner_user_id=owner,
                                    )
                                    session.add(profile)
                                    session.flush()
                                    session.add(Activity(profile_id=profile.id, owner_user_id=owner, event="Profile Created",
                                                          detail=f"Extracted via {config.LLM_PROVIDER}",
                                                          created_by_user_id=current_user["id"]))
                                    raw = get_owned(session, RawMessage, msg.id, owner)
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
            owned(select(RawMessage).where(RawMessage.processed.is_(True)), RawMessage, owner)
            .order_by(RawMessage.created_at.desc())
        ).all()[:30]
        profiles_by_msg = {
            p.source_message_id: p
            for p in session.scalars(
                owned(select(Profile).where(Profile.source_message_id.isnot(None)), Profile, owner)
            ).all()
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
                    raw = get_owned(session, RawMessage, m.id, owner)
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
                                raw = get_owned(session, RawMessage, msg.id, owner)
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
                                raw = get_owned(session, RawMessage, msg.id, owner)
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
