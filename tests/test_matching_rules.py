from soulmatch.matching.rules import evaluate_match
from soulmatch.models import Profile


def make_profile(**kwargs) -> Profile:
    defaults = dict(
        age=26, height_cm=160, religion="Hindu", caste="Brahmin", gothram="Bharadwaja",
        current_location="Bangalore", country="India", food_preference="Vegetarian",
        marital_status="Never Married",
    )
    defaults.update(kwargs)
    return Profile(**defaults)


def test_good_match_recommended():
    bride = make_profile(gender="Bride")
    groom = make_profile(gender="Groom", age=29, height_cm=172, gothram="Kashyapa")
    outcome = evaluate_match(bride, groom)
    assert outcome.mandatory_passed
    assert outcome.recommended
    assert outcome.score > 50


def test_religion_mismatch_blocks_mandatory():
    bride = make_profile(gender="Bride", religion="Hindu")
    groom = make_profile(gender="Groom", religion="Christian")
    outcome = evaluate_match(bride, groom)
    assert not outcome.mandatory_passed
    assert not outcome.recommended


def test_same_gothram_blocks_mandatory():
    bride = make_profile(gender="Bride", gothram="Bharadwaja")
    groom = make_profile(gender="Groom", gothram="Bharadwaja")
    outcome = evaluate_match(bride, groom)
    assert not outcome.mandatory_passed


def test_missing_fields_are_skipped_not_failed():
    bride = make_profile(gender="Bride", height_cm=None)
    groom = make_profile(gender="Groom", height_cm=None)
    outcome = evaluate_match(bride, groom)
    height_result = next(r for r in outcome.results if r.name == "Height")
    assert height_result.passed
    assert "height_cm" in outcome.missing_fields
