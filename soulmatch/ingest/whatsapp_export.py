"""Parser for WhatsApp 'Export Chat' files (.txt, or .zip with media).

Handles both common line formats:
  Android:  12/05/2024, 10:15 pm - Ramesh Kumar: message text
  iOS:      [12/05/24, 10:15:33 PM] Ramesh Kumar: message text

Messages can span multiple lines; continuation lines are appended to the
previous message. Lines with a timestamp but no "Sender: " part are system
messages (group created, member added, ...).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Invisible direction marks WhatsApp sprinkles into exports
_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‬﻿"), None)

_ANDROID = re.compile(
    r"^(?P<date>\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2})\s*(?P<ampm>[AaPp]\.?[Mm]\.?)?\s+-\s+(?P<rest>.*)$"
)
_IOS = re.compile(
    r"^\[(?P<date>\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<ampm>[AaPp][Mm])?\]\s*(?P<rest>.*)$"
)

_MEDIA_PATTERNS = [
    re.compile(r"<Media omitted>", re.I),
    re.compile(r"<attached:\s*(?P<file>[^>]+)>", re.I),
    re.compile(r"(?P<file>\S+)\s+\(file attached\)", re.I),
    re.compile(r"image omitted|video omitted|document omitted|audio omitted|sticker omitted", re.I),
]


@dataclass
class ParsedMessage:
    sent_at: datetime | None
    sender: str | None
    content: str
    media_filename: str | None = None
    is_system: bool = False
    lines: list[str] = field(default_factory=list, repr=False)


def _parse_date(date_str: str, time_str: str, ampm: str | None) -> datetime | None:
    parts = re.split(r"[/.\-]", date_str)
    a, b, c = (int(p) for p in parts)
    if c < 100:
        c += 2000
    # Indian exports are day-first; fall back if the "day" can't be a day.
    if a > 12:
        day, month = a, b
    elif b > 12:
        day, month = b, a
    else:
        day, month = a, b
    tparts = [int(x) for x in time_str.split(":")]
    hour, minute = tparts[0], tparts[1]
    second = tparts[2] if len(tparts) > 2 else 0
    if ampm:
        ap = ampm.replace(".", "").lower()
        if ap == "pm" and hour < 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
    try:
        return datetime(c, month, day, hour, minute, second)
    except ValueError:
        return None


def _detect_media(text: str) -> str | None:
    for pat in _MEDIA_PATTERNS:
        m = pat.search(text)
        if m:
            return (m.groupdict() or {}).get("file")
    return None


def parse_chat_text(text: str, keep_system: bool = False) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    current: ParsedMessage | None = None

    for raw_line in text.splitlines():
        line = raw_line.translate(_INVISIBLE).rstrip()
        m = _ANDROID.match(line) or _IOS.match(line)
        if not m:
            if current is not None and line:
                current.lines.append(line)
            continue

        if current is not None:
            current.content = "\n".join(current.lines).strip()
            messages.append(current)

        sent_at = _parse_date(m.group("date"), m.group("time"), m.group("ampm"))
        rest = m.group("rest")
        sender, sep, body = rest.partition(": ")
        if sep:
            current = ParsedMessage(sent_at=sent_at, sender=sender.strip(), content="", lines=[body])
        else:
            current = ParsedMessage(sent_at=sent_at, sender=None, content="", is_system=True, lines=[rest])

    if current is not None:
        current.content = "\n".join(current.lines).strip()
        messages.append(current)

    for msg in messages:
        msg.media_filename = _detect_media(msg.content)

    if not keep_system:
        messages = [m for m in messages if not m.is_system]
    return messages


def parse_export(data: bytes, filename: str) -> tuple[list[ParsedMessage], dict[str, bytes]]:
    """Parse an uploaded export. Returns (messages, media_files{name: bytes})."""
    media: dict[str, bytes] = {}
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not txt_names:
                raise ValueError("No .txt chat file found inside the zip")
            # WhatsApp names it "_chat.txt" (iOS) or "WhatsApp Chat with X.txt" (Android)
            txt_name = next((n for n in txt_names if "chat" in n.lower()), txt_names[0])
            text = zf.read(txt_name).decode("utf-8", errors="replace")
            for name in zf.namelist():
                if name != txt_name and not name.endswith("/"):
                    media[Path(name).name] = zf.read(name)
    else:
        text = data.decode("utf-8", errors="replace")
    return parse_chat_text(text), media
