from soulmatch.models import Profile
from soulmatch.preferences import CandidatePreferences, filter_candidates, matches_preferences


def _profile(**kwargs) -> Profile:
    defaults = dict(full_name="Test", gender="Groom")
    defaults.update(kwargs)
    return Profile(**defaults)


def test_default_preferences_match_everything():
    p = _profile()
    assert matches_preferences(p, CandidatePreferences())
    assert CandidatePreferences().is_default()


def test_age_range_excludes_out_of_range():
    p = _profile(age=25)
    assert matches_preferences(p, CandidatePreferences(min_age=28, max_age=35)) is False
    assert matches_preferences(p, CandidatePreferences(min_age=20, max_age=30)) is True


def test_age_filter_does_not_exclude_missing_data():
    p = _profile(age=None)
    assert matches_preferences(p, CandidatePreferences(min_age=28, max_age=35)) is True


def test_height_range_excludes_out_of_range():
    p = _profile(height_cm=160.0)
    assert matches_preferences(p, CandidatePreferences(min_height_cm=165, max_height_cm=180)) is False
    assert matches_preferences(p, CandidatePreferences(min_height_cm=150, max_height_cm=170)) is True


def test_location_contains_is_case_insensitive_substring():
    p = _profile(current_location="Bangalore")
    assert matches_preferences(p, CandidatePreferences(location_contains="bang")) is True
    assert matches_preferences(p, CandidatePreferences(location_contains="chennai")) is False


def test_location_filter_does_not_exclude_missing_data():
    p = _profile(current_location=None)
    assert matches_preferences(p, CandidatePreferences(location_contains="bangalore")) is True


def test_religion_and_caste_contains():
    p = _profile(religion="Hindu", caste="Brahmin")
    assert matches_preferences(p, CandidatePreferences(religion_contains="hin", caste_contains="brah")) is True
    assert matches_preferences(p, CandidatePreferences(caste_contains="reddy")) is False


def test_marital_status_and_food_preference_exact_match():
    p = _profile(marital_status="Never Married", food_preference="Vegetarian")
    assert matches_preferences(p, CandidatePreferences(marital_status="Never Married")) is True
    assert matches_preferences(p, CandidatePreferences(marital_status="Divorced")) is False
    assert matches_preferences(p, CandidatePreferences(food_preference="Non-Vegetarian")) is False


def test_horoscope_available_filter():
    available = _profile(horoscope_available=True)
    pending = _profile(horoscope_available=False)
    unknown = _profile(horoscope_available=None)
    assert matches_preferences(available, CandidatePreferences(horoscope_available=True)) is True
    assert matches_preferences(pending, CandidatePreferences(horoscope_available=True)) is False
    # unset horoscope_available is treated as "unknown", not "pending" -- never excluded
    assert matches_preferences(unknown, CandidatePreferences(horoscope_available=True)) is True


def test_filter_candidates_applies_across_a_list():
    profiles = [_profile(age=25), _profile(age=32), _profile(age=40)]
    result = filter_candidates(profiles, CandidatePreferences(min_age=28, max_age=35))
    assert len(result) == 1
    assert result[0].age == 32


def test_combined_filters_all_must_pass():
    p = _profile(age=30, height_cm=170, current_location="Hyderabad", religion="Hindu")
    prefs = CandidatePreferences(min_age=25, max_age=35, min_height_cm=165, max_height_cm=180,
                                  location_contains="hyderabad", religion_contains="hindu")
    assert matches_preferences(p, prefs) is True
    prefs_fail = CandidatePreferences(min_age=25, max_age=35, religion_contains="muslim")
    assert matches_preferences(p, prefs_fail) is False
