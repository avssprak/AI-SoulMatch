from datetime import date

import pytest

from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, full_compatibility


def test_build_chart_known_city():
    chart = build_chart(BirthDetails(date(1995, 6, 15), "10:30", "Bangalore"))
    assert 0 <= chart.nakshatra <= 26
    assert 0 <= chart.rashi <= 11
    assert 0 <= chart.lagna <= 11
    assert 1 <= chart.pada <= 4


def test_build_chart_unknown_place_raises():
    with pytest.raises(AstrologyError):
        build_chart(BirthDetails(date(1995, 6, 15), "10:30", "Nonexistentville9999"))


def test_build_chart_bad_time_raises():
    with pytest.raises(AstrologyError):
        build_chart(BirthDetails(date(1995, 6, 15), "not-a-time", "Bangalore"))


def test_full_compatibility_end_to_end():
    groom_chart = build_chart(BirthDetails(date(1992, 3, 10), "06:00", "Chennai"))
    bride_chart = build_chart(BirthDetails(date(1995, 9, 22), "18:45", "Chennai"))
    result = full_compatibility(groom_chart, bride_chart)
    assert 0 <= result["overall_score"] <= 36
    assert result["overall_verdict"] in ("Not recommended", "Average", "Good", "Excellent")
    assert "groom_chart" in result and "bride_chart" in result
