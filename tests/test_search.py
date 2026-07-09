from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from soulmatch import search
from soulmatch.extraction import llm
from soulmatch.models import Base, Profile


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session):
    session.add_all([
        Profile(full_name="Priya Sharma", gender="Bride", age=26, religion="Hindu",
                caste="Brahmin", current_location="Bangalore", qualification="B.Tech",
                occupation="Software Engineer", food_preference="Vegetarian",
                horoscope_available=True),
        Profile(full_name="Anjali Rao", gender="Bride", age=32, religion="Hindu",
                caste="Reddy", current_location="Chennai", qualification="MBA",
                occupation="Manager", food_preference="Non-Vegetarian",
                horoscope_available=False),
        Profile(full_name="Arjun Kumar", gender="Groom", age=29, religion="Hindu",
                caste="Brahmin", current_location="Bangalore", qualification="MBBS",
                occupation="Doctor", food_preference="Vegetarian",
                horoscope_available=True),
    ])
    session.commit()


def test_mock_parse_gender_and_age():
    session = _memory_session()
    _seed(session)
    filters = search._mock_parse_query(session, "brides below 30")
    assert filters["gender"] == "Bride"
    assert filters["max_age"] == 30


def test_mock_parse_matches_known_db_values():
    session = _memory_session()
    _seed(session)
    filters = search._mock_parse_query(session, "Brahmin grooms in Bangalore")
    assert filters["gender"] == "Groom"
    assert filters["caste"] == "Brahmin"
    assert filters["current_location"] == "Bangalore"


def test_mock_parse_horoscope_pending():
    session = _memory_session()
    _seed(session)
    filters = search._mock_parse_query(session, "brides with pending horoscope")
    assert filters["gender"] == "Bride"
    assert filters["horoscope_available"] is False


def test_mock_parse_food_preference():
    session = _memory_session()
    _seed(session)
    filters = search._mock_parse_query(session, "vegetarian grooms")
    assert filters["food_preference"] == "Vegetarian"


def test_apply_filters_gender_and_caste():
    session = _memory_session()
    _seed(session)
    results = search.apply_filters(session, {"gender": "Bride", "caste": "Brahmin"})
    assert len(results) == 1
    assert results[0].full_name == "Priya Sharma"


def test_apply_filters_age_range():
    session = _memory_session()
    _seed(session)
    results = search.apply_filters(session, {"gender": "Bride", "max_age": 28})
    assert len(results) == 1
    assert results[0].full_name == "Priya Sharma"


def test_apply_filters_no_filters_returns_all():
    session = _memory_session()
    _seed(session)
    results = search.apply_filters(session, {})
    assert len(results) == 3


def test_apply_filters_horoscope_available():
    session = _memory_session()
    _seed(session)
    results = search.apply_filters(session, {"horoscope_available": False})
    assert len(results) == 1
    assert results[0].full_name == "Anjali Rao"


def test_describe_filters():
    assert search.describe_filters({}) == "no filters recognized — showing all profiles"
    desc = search.describe_filters({"gender": "Bride", "max_age": None, "caste": "Brahmin"})
    assert "gender" in desc and "caste" in desc and "max_age" not in desc


def test_llm_parse_query_via_monkeypatch(monkeypatch):
    def fake_complete_json(prompt, provider=None):
        return {"gender": "Bride", "caste": "Brahmin", "min_age": "25", "max_age": None,
                "religion": None, "current_location": None, "country": None,
                "qualification_contains": None, "occupation_contains": None,
                "food_preference": None, "marital_status": None,
                "horoscope_available": "true", "stage": "Interested"}

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    session = _memory_session()
    filters = search.parse_query(session, "Brahmin brides above 25 with horoscope", provider="anthropic")
    assert filters["gender"] == "Bride"
    assert filters["min_age"] == 25
    assert filters["horoscope_available"] is True
    assert filters["stage"] == "Interested"
