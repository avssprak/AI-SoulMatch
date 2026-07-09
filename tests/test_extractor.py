from datetime import date

from soulmatch.extraction.extractor import extract_profile, is_likely_profile


def test_is_likely_profile_positive():
    text = (
        "Looking for alliance for my daughter. Age 26, height 5'4\", B.Tech, "
        "working as software engineer, salary 12 LPA, Brahmin caste, gothram Bharadwaja"
    )
    assert is_likely_profile(text)


def test_is_likely_profile_negative():
    assert not is_likely_profile("Good morning everyone!")


def test_mock_extract_basic_fields():
    text = (
        "Name: Priya Sharma\nAge: 26\nHeight 5'4\"\nDOB: 15/06/1998\n"
        "Bride, Vegetarian, phone 9876543210, B.Tech from VTU"
    )
    data = extract_profile(text, provider="mock")
    assert data["full_name"] == "Priya Sharma"
    assert data["age"] == 26
    assert data["gender"] == "Bride"
    assert data["food_preference"] == "Vegetarian"
    assert data["phone"] == "9876543210"
    assert data["dob"] == date(1998, 6, 15)
    assert data["height_cm"] is not None
