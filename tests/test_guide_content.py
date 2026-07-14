from soulmatch.guide_content import SECTION_ORDER, SECTIONS


def test_every_section_in_order_exists():
    assert set(SECTION_ORDER) == set(SECTIONS.keys())


def test_sections_have_title_and_nonempty_body():
    for key in SECTION_ORDER:
        title, body = SECTIONS[key]
        assert title.strip()
        assert body.strip()


def test_whatsapp_export_instructions_present():
    _, body = SECTIONS["candidates"]
    assert "Export chat" in body or "Export Chat" in body
    assert "Android" in body and "iPhone" in body
