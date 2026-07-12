from dataclasses import dataclass

from soulmatch import ui


@dataclass
class _FakeUploadedFile:
    name: str
    size: int


def test_check_upload_size_allows_none():
    assert ui.check_upload_size(None) is True


def test_check_upload_size_allows_within_limit():
    small = _FakeUploadedFile(name="biodata.pdf", size=1_000_000)
    assert ui.check_upload_size(small) is True


def test_check_upload_size_rejects_over_limit():
    big = _FakeUploadedFile(name="huge.pdf", size=ui.MAX_UPLOAD_BYTES + 1)
    assert ui.check_upload_size(big) is False


def test_check_upload_size_allows_exactly_at_limit():
    exact = _FakeUploadedFile(name="exact.pdf", size=ui.MAX_UPLOAD_BYTES)
    assert ui.check_upload_size(exact) is True
