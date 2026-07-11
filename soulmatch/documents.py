"""Module 3 — Document Repository: store biodata/horoscope PDFs, photos, etc.
against a profile, on local disk under UPLOAD_DIR/<profile_id>/.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from . import config
from .models import Document

DOCUMENT_KINDS = ["biodata", "horoscope", "photo", "family_photo", "certificate", "other"]


def _profile_dir(profile_id: int) -> Path:
    d = config.UPLOAD_DIR / str(profile_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_document(
    session: Session, profile_id: int, kind: str, filename: str, data: bytes,
    created_by_user_id: int | None = None, owner_user_id: int | None = None,
) -> Document:
    if kind not in DOCUMENT_KINDS:
        raise ValueError(f"Unknown document kind: {kind}")
    safe_name = os.path.basename(filename) or "upload"
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = _profile_dir(profile_id) / stored_name
    dest.write_bytes(data)

    doc = Document(
        profile_id=profile_id, kind=kind, filename=safe_name, path=str(dest),
        created_by_user_id=created_by_user_id,
        owner_user_id=owner_user_id if owner_user_id is not None else created_by_user_id,
    )
    session.add(doc)
    session.flush()
    return doc


def read_document(doc: Document) -> bytes:
    return Path(doc.path).read_bytes()


def delete_document(session: Session, doc: Document) -> None:
    path = Path(doc.path)
    if path.exists():
        path.unlink()
    session.delete(doc)
