from soulmatch.models import Profile
from soulmatch.summary import profile_summary_html


def test_summary_includes_name_and_key_fields():
    profile = Profile(
        full_name="Priya Sharma", gender="Bride", age=26, religion="Hindu", caste="Brahmin",
        qualification="B.Tech", occupation="Engineer", current_location="Bangalore",
        stage="Interested", notes="Called twice, parents are cautious",
    )
    html = profile_summary_html(profile)
    assert "Priya Sharma" in html
    assert "Bangalore" in html
    assert "B.Tech" in html


def test_summary_omits_internal_fields():
    profile = Profile(
        full_name="Priya Sharma", gender="Bride", stage="Interested",
        notes="Called twice, parents are cautious", phone="9876543210",
    )
    html = profile_summary_html(profile)
    assert "Interested" not in html
    assert "Called twice" not in html
    assert "9876543210" not in html


def test_summary_includes_chart_when_provided():
    profile = Profile(full_name="Priya Sharma", gender="Bride")
    html = profile_summary_html(profile, chart={"nakshatra": "Ashwini", "rashi": "Mesha", "lagna": "Simha"})
    assert "Ashwini" in html
    assert "Mesha" in html


def test_summary_no_chart_section_when_not_computed():
    profile = Profile(full_name="Priya Sharma", gender="Bride")
    html = profile_summary_html(profile)
    assert "Astrology" not in html
