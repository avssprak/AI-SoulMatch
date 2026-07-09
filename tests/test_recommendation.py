from soulmatch import recommendation
from soulmatch.extraction import llm
from soulmatch.models import Profile


def make_bride():
    return Profile(full_name="Priya Sharma", gender="Bride", age=26,
                    food_preference="Vegetarian", occupation="Software Engineer")


def make_groom():
    return Profile(full_name="Arjun Rao", gender="Groom", age=29,
                    food_preference="Vegetarian", occupation="Manager")


def test_mock_recommendation_good_match():
    bride, groom = make_bride(), make_groom()
    practical = {"score": 90.0, "recommended": True, "strengths": ["Same location"], "weaknesses": []}
    astro = {"overall_score": 30.0, "overall_verdict": "Good", "dosha_flags": []}

    rec = recommendation.generate_recommendation(bride, groom, practical, astro, provider="mock")

    assert rec["final_recommendation"] == "Recommended"
    assert rec["_provider"] == "mock"
    assert rec["risk_indicators"] == []
    assert "Priya Sharma" in rec["summary"]
    assert "Same food preference" in rec["lifestyle_compatibility"]


def test_mock_recommendation_flags_low_astrology_score():
    bride, groom = make_bride(), make_groom()
    practical = {"score": 80.0, "recommended": True, "strengths": [], "weaknesses": []}
    astro = {"overall_score": 10.0, "overall_verdict": "Not recommended", "dosha_flags": ["Nadi dosha"]}

    rec = recommendation.generate_recommendation(bride, groom, practical, astro, provider="mock")

    assert rec["final_recommendation"] == "Not Recommended"
    assert any("Low astrology compatibility" in c for c in rec["concerns"])
    assert "Nadi dosha" in rec["risk_indicators"]


def test_mock_recommendation_without_astrology():
    bride, groom = make_bride(), make_groom()
    practical = {"score": 70.0, "recommended": True, "strengths": ["Good match"], "weaknesses": []}

    rec = recommendation.generate_recommendation(bride, groom, practical, None, provider="mock")

    assert rec["final_recommendation"] == "Recommended"
    assert "astrology" not in rec["summary"].lower()


def test_llm_provider_path_uses_complete_json(monkeypatch):
    captured_prompt = {}

    def fake_complete_json(prompt, provider=None):
        captured_prompt["prompt"] = prompt
        captured_prompt["provider"] = provider
        return {
            "summary": "Strong match overall.",
            "strengths": "Great career alignment",  # deliberately not a list — _clean should wrap it
            "concerns": [],
            "questions_for_families": ["Discuss timelines"],
            "family_compatibility": "Good",
            "lifestyle_compatibility": "Good",
            "career_compatibility": "Good",
            "risk_indicators": [],
            "final_recommendation": "Recommended",
        }

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)

    bride, groom = make_bride(), make_groom()
    practical = {"score": 88.0, "recommended": True, "strengths": [], "weaknesses": []}
    rec = recommendation.generate_recommendation(bride, groom, practical, None, provider="anthropic")

    assert captured_prompt["provider"] == "anthropic"
    assert "Priya Sharma" in captured_prompt["prompt"]
    assert rec["strengths"] == ["Great career alignment"]
    assert rec["final_recommendation"] == "Recommended"
    assert rec["_provider"] == "anthropic"
