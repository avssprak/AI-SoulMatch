"""Astrology Agent: orchestrates geocoding, chart calculation, koota scoring
and dosha checks into the results the rest of the app consumes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from . import dosha as dosha_mod
from . import geo
from .ephemeris import Chart, compute_chart
from .koota import PersonInput, ashta_koota


class AstrologyError(RuntimeError):
    pass


@dataclass
class BirthDetails:
    dob: date
    birth_time: str  # "HH:MM"
    birth_place: str


def build_chart(details: BirthDetails) -> Chart:
    place = geo.lookup(details.birth_place)
    if place is None:
        raise AstrologyError(
            f"Could not resolve birth place '{details.birth_place}'. "
            "Try a more specific or well-known nearby city name."
        )
    try:
        hour, minute = (int(x) for x in details.birth_time.split(":")[:2])
    except (ValueError, AttributeError) as e:
        raise AstrologyError(f"Invalid birth time '{details.birth_time}', expected HH:MM") from e

    local_dt = datetime(details.dob.year, details.dob.month, details.dob.day, hour, minute)
    return compute_chart(local_dt, place.latitude, place.longitude, place.timezone)


def chart_summary(chart: Chart) -> dict:
    return {
        "nakshatra": chart.nakshatra_name,
        "pada": chart.pada,
        "rashi": chart.rashi_name,
        "lagna": chart.lagna_name,
        "moon_longitude": round(chart.moon_longitude, 2),
    }


def full_compatibility(groom_chart: Chart, bride_chart: Chart) -> dict:
    groom_in = PersonInput(groom_chart.nakshatra, groom_chart.rashi, groom_chart.moon_longitude)
    bride_in = PersonInput(bride_chart.nakshatra, bride_chart.rashi, bride_chart.moon_longitude)

    koota = ashta_koota(groom_in, bride_in)
    kuja_g = dosha_mod.kuja_dosha(groom_chart)
    kuja_b = dosha_mod.kuja_dosha(bride_chart)
    rajju = dosha_mod.rajju(groom_chart.nakshatra, bride_chart.nakshatra)
    vedha = dosha_mod.vedha(groom_chart.nakshatra, bride_chart.nakshatra)

    kuja_conflict = kuja_g["present"] != kuja_b["present"]

    dosha_flags = [
        f"Manglik mismatch (groom={kuja_g['present']}, bride={kuja_b['present']})"
        if kuja_conflict else None,
        "Rajju dosha (same body part)" if rajju["dosha"] else None,
        "Vedha dosha" if vedha["dosha"] else None,
        "Nadi dosha" if koota["kootas"]["Nadi"]["score"] == 0 else None,
        "Bhakoot dosha" if koota["kootas"]["Bhakoot"]["score"] == 0 else None,
    ]
    dosha_flags = [f for f in dosha_flags if f]

    return {
        "groom_chart": chart_summary(groom_chart),
        "bride_chart": chart_summary(bride_chart),
        "koota": koota,
        "kuja_dosha": {"groom": kuja_g, "bride": kuja_b},
        "rajju": rajju,
        "vedha": vedha,
        "dosha_flags": dosha_flags,
        "overall_score": koota["total"],
        "overall_max": koota["max"],
        "overall_verdict": koota["verdict"],
    }
