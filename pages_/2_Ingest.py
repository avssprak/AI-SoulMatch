from datetime import date

import streamlit as st

from soulmatch import config
from soulmatch.db import get_session
from soulmatch.duplicates import find_duplicate_candidates
from soulmatch.extraction.extractor import extract_profile, is_likely_profile
from soulmatch.extraction.llm import LLMError
from soulmatch.ingest.whatsapp_export import parse_export
from soulmatch.models import Activity, Profile, RawMessage

st.title("📥 Ingest — WhatsApp Chat Export")

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
            with get_session() as session:
                msg = RawMessage(
                    source="manual",
                    sender=manual_sender or None,
                    content=manual_text.strip(),
                )
                session.add(msg)
                session.commit()
            st.success("Message added. Scroll down to process it.")
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
                for m in messages:
                    session.add(RawMessage(
                        source="whatsapp_export",
                        chat_name=uploaded.name,
                        sender=m.sender,
                        sent_at=m.sent_at,
                        content=m.content,
                        media_filename=m.media_filename,
                        is_system=m.is_system,
                    ))
                session.commit()
            st.success("Imported. Process them below.")
            st.rerun()

st.divider()
st.subheader("Unprocessed Messages")

with get_session() as session:
    from sqlalchemy import select

    unprocessed = session.scalars(
        select(RawMessage).where(RawMessage.processed.is_(False)).order_by(RawMessage.created_at.desc())
    ).all()

st.caption(f"{len(unprocessed)} unprocessed message(s). Provider: **{config.LLM_PROVIDER}**")

if not unprocessed:
    st.info("Nothing to process. Upload an export above.")
else:
    only_likely = st.checkbox("Only show messages that look like profiles", value=True)
    shown = [m for m in unprocessed if not only_likely or is_likely_profile(m.content)]

    for msg in shown[:30]:
        pending_key = f"pending_extract_{msg.id}"
        with st.expander(f"{msg.sender or 'Unknown'} — {msg.content[:80]}"):
            st.text(msg.content)

            if pending_key not in st.session_state:
                col1, col2 = st.columns([1, 1])
                with col1:
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
                with col2:
                    if st.button("Mark as not a profile / skip", key=f"skip_{msg.id}"):
                        with get_session() as session:
                            raw = session.get(RawMessage, msg.id)
                            raw.processed = True
                            session.commit()
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
                            st.markdown(
                                f"- **#{d.profile.id} {d.profile.full_name or 'Unnamed'}** "
                                f"({d.score}% match) — {'; '.join(d.reasons)}"
                            )

                col1, col2 = st.columns([1, 1])
                with col1:
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
                                                  detail=f"Extracted via {config.LLM_PROVIDER}"))
                            raw = session.get(RawMessage, msg.id)
                            raw.processed = True
                            session.commit()
                        del st.session_state[pending_key]
                        st.success("Profile created.")
                        st.rerun()
                with col2:
                    if st.button("Discard extraction", key=f"discard_{msg.id}"):
                        del st.session_state[pending_key]
                        st.rerun()
