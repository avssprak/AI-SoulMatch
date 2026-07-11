"""Parser for arbitrary profile lists: plain .txt or .pdf, not tied to any
chat export format. Unlike the WhatsApp parser there's no reliable per-message
delimiter, so we split on blank-line paragraph breaks and let the extraction
agent (and the "profile-like" pre-filter) sort out which chunks are real
biodata entries.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader


def _extract_text(data: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="replace")


def split_into_chunks(text: str) -> list[str]:
    """Split free-form text into candidate profile blocks on blank lines."""
    raw_chunks = re.split(r"\n\s*\n+", text)
    return [c.strip() for c in raw_chunks if c.strip()]


def parse_document(data: bytes, filename: str) -> list[str]:
    """Parse an uploaded .txt/.pdf into a list of candidate profile text blocks."""
    text = _extract_text(data, filename)
    return split_into_chunks(text)
