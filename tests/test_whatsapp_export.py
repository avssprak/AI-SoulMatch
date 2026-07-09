from soulmatch.ingest.whatsapp_export import parse_chat_text


def test_android_format_basic():
    text = (
        "12/05/2024, 10:15 pm - Ramesh Kumar: Looking for alliance for my daughter\n"
        "Age 26, height 5'4\", B.Tech, working in Bangalore\n"
        "13/05/2024, 9:00 am - Suresh: Sounds good, share biodata"
    )
    messages = parse_chat_text(text)
    assert len(messages) == 2
    assert messages[0].sender == "Ramesh Kumar"
    assert "Age 26" in messages[0].content
    assert "Looking for alliance" in messages[0].content
    assert messages[0].sent_at.year == 2024
    assert messages[0].sent_at.hour == 22
    assert messages[1].sender == "Suresh"
    assert messages[1].sent_at.hour == 9


def test_ios_format_basic():
    text = "[12/05/24, 10:15:33 PM] Ramesh Kumar: Bride profile, age 24, Brahmin, Iyer"
    messages = parse_chat_text(text)
    assert len(messages) == 1
    assert messages[0].sender == "Ramesh Kumar"
    assert messages[0].sent_at.hour == 22


def test_system_messages_excluded_by_default():
    text = (
        "12/05/2024, 10:15 pm - Messages and calls are end-to-end encrypted\n"
        "12/05/2024, 10:16 pm - Ramesh Kumar: Real message here"
    )
    messages = parse_chat_text(text)
    assert len(messages) == 1
    assert messages[0].sender == "Ramesh Kumar"


def test_media_detection():
    text = "12/05/2024, 10:15 pm - Ramesh Kumar: <Media omitted>"
    messages = parse_chat_text(text)
    assert messages[0].media_filename is None or "omitted" not in (messages[0].media_filename or "")
