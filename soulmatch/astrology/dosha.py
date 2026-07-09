"""Dosha checks beyond the eight kootas: Kuja (Manglik), Rajju, Vedha."""

from __future__ import annotations

from .ephemeris import NAKSHATRAS, Chart

# Houses where Mars causes Kuja dosha (South Indian tradition includes 2nd)
_KUJA_HOUSES = {1, 2, 4, 7, 8, 12}

# Rajju group per (nakshatra % 9): Pada, Kati, Nabhi, Kantha, Siro zigzag
_RAJJU_CYCLE = [0, 1, 2, 3, 4, 3, 2, 1, 0]
_RAJJU_NAMES = ["Pada (feet)", "Kati (waist)", "Nabhi (navel)", "Kantha (neck)", "Siro (head)"]

# Standard 13 vedha (mutual affliction) nakshatra pairs; Chitra has none
_VEDHA_PAIRS = {
    frozenset(p) for p in [
        (0, 17), (1, 16), (2, 15), (3, 14), (4, 22), (5, 21), (6, 20),
        (7, 19), (8, 18), (9, 26), (10, 25), (11, 24), (12, 23),
    ]
}


def kuja_dosha(chart: Chart) -> dict:
    """Check Mars placement from lagna, moon and Venus."""
    findings = {}
    for ref_name, ref_sign in (
        ("Lagna", chart.lagna),
        ("Moon", chart.rashi),
        ("Venus", chart.planet_sign("Venus")),
    ):
        house = chart.planet_house("Mars", ref_sign)
        findings[ref_name] = {"house": house, "dosha": house in _KUJA_HOUSES}
    present = any(v["dosha"] for v in findings.values())
    return {
        "present": present,
        "from": findings,
        "note": "Kuja dosha is commonly considered cancelled when both partners have it.",
    }


def rajju(groom_nak: int, bride_nak: int) -> dict:
    g, b = _RAJJU_CYCLE[groom_nak % 9], _RAJJU_CYCLE[bride_nak % 9]
    return {
        "groom": _RAJJU_NAMES[g],
        "bride": _RAJJU_NAMES[b],
        "dosha": g == b,
        "note": "Same rajju is considered inauspicious" if g == b else "Different rajju — no dosha",
    }


def vedha(groom_nak: int, bride_nak: int) -> dict:
    afflicted = frozenset((groom_nak, bride_nak)) in _VEDHA_PAIRS
    return {
        "groom": NAKSHATRAS[groom_nak],
        "bride": NAKSHATRAS[bride_nak],
        "dosha": afflicted,
        "note": "Vedha pair — mutually afflicting nakshatras" if afflicted else "No vedha",
    }
