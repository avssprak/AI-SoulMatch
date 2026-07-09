from datetime import date

import pytest

from soulmatch.astrology.engine import AstrologyError, BirthDetails, build_chart, chart_summary, full_compatibility
from soulmatch.astrology.ephemeris import NAKSHATRAS, NAKSHATRAS_TE, RASHIS, RASHIS_TE


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


def test_telugu_name_lists_are_correctly_sized():
    assert len(NAKSHATRAS_TE) == len(NAKSHATRAS) == 27
    assert len(RASHIS_TE) == len(RASHIS) == 12
    assert all(isinstance(n, str) and n for n in NAKSHATRAS_TE)
    assert all(isinstance(r, str) and r for r in RASHIS_TE)


def test_chart_summary_includes_telugu_names():
    chart = build_chart(BirthDetails(date(1998, 6, 15), "10:30", "Hyderabad"))
    summary = chart_summary(chart)
    assert summary["nakshatra_te"] == NAKSHATRAS_TE[chart.nakshatra]
    assert summary["rashi_te"] == RASHIS_TE[chart.rashi]
    assert summary["lagna_te"] == RASHIS_TE[chart.lagna]


def test_known_telugu_spot_checks():
    # Rohini (index 3) and Krittika (index 2) are well-known, unambiguous names.
    assert NAKSHATRAS_TE[3] == "రోహిణి"
    assert NAKSHATRAS_TE[2] == "కృత్తిక"
    # Mesha (index 0) and Meena (index 11)
    assert RASHIS_TE[0] == "మేషం"
    assert RASHIS_TE[11] == "మీనం"
