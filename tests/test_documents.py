import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import config, documents
from soulmatch.models import Base, Profile


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        profile = Profile(full_name="Priya Sharma", gender="Bride")
        s.add(profile)
        s.commit()
        s.profile_id = profile.id  # stash for tests
        yield s


def test_save_and_read_document(session):
    doc = documents.save_document(session, session.profile_id, "biodata", "bio.pdf", b"%PDF-fake-content")
    session.commit()

    assert doc.filename == "bio.pdf"
    assert doc.kind == "biodata"
    assert documents.read_document(doc) == b"%PDF-fake-content"


def test_save_document_rejects_unknown_kind(session):
    with pytest.raises(ValueError):
        documents.save_document(session, session.profile_id, "not_a_kind", "x.pdf", b"data")


def test_save_document_sanitizes_path_traversal(session):
    doc = documents.save_document(session, session.profile_id, "photo", "../../etc/passwd", b"data")
    session.commit()
    # stored filename must not escape the profile's upload directory
    assert config.UPLOAD_DIR.resolve() in __import__("pathlib").Path(doc.path).resolve().parents
    assert doc.filename == "passwd"


def test_delete_document_removes_file(session):
    doc = documents.save_document(session, session.profile_id, "photo", "pic.jpg", b"jpgdata")
    session.commit()
    from pathlib import Path

    path = Path(doc.path)
    assert path.exists()

    documents.delete_document(session, doc)
    session.commit()
    assert not path.exists()
