"""Sidereal (Lahiri) chart computation via Swiss Ephemeris.

Uses the built-in Moshier ephemeris (FLG_MOSEPH) so no ephemeris data files
need to be shipped; precision is far beyond what nakshatra/rashi/lagna
determination requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import swisseph as swe

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]

RASHIS = [
    "Mesha (Aries)", "Vrishabha (Taurus)", "Mithuna (Gemini)",
    "Karka (Cancer)", "Simha (Leo)", "Kanya (Virgo)", "Tula (Libra)",
    "Vrischika (Scorpio)", "Dhanu (Sagittarius)", "Makara (Capricorn)",
    "Kumbha (Aquarius)", "Meena (Pisces)",
]

PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
}

_FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL

NAK_SPAN = 360.0 / 27.0  # 13°20'


@dataclass
class Chart:
    moon_longitude: float          # sidereal, 0-360
    nakshatra: int                 # 0-26
    pada: int                      # 1-4
    rashi: int                     # 0-11 (moon sign)
    lagna: int                     # 0-11 (ascendant sign)
    planet_longitudes: dict[str, float]
    utc: datetime

    @property
    def nakshatra_name(self) -> str:
        return NAKSHATRAS[self.nakshatra]

    @property
    def rashi_name(self) -> str:
        return RASHIS[self.rashi]

    @property
    def lagna_name(self) -> str:
        return RASHIS[self.lagna]

    def planet_sign(self, planet: str) -> int:
        return int(self.planet_longitudes[planet] // 30)

    def planet_house(self, planet: str, from_sign: int) -> int:
        """Whole-sign house (1-12) of a planet counted from a reference sign."""
        return (self.planet_sign(planet) - from_sign) % 12 + 1


def compute_chart(local_dt: datetime, latitude: float, longitude: float, tz_name: str) -> Chart:
    aware = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    utc = aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = swe.julday(
        utc.year, utc.month, utc.day,
        utc.hour + utc.minute / 60 + utc.second / 3600,
    )

    positions: dict[str, float] = {}
    for name, code in PLANETS.items():
        result, _ = swe.calc_ut(jd, code, _FLAGS)
        positions[name] = result[0] % 360.0

    moon = positions["Moon"]
    nak = int(moon // NAK_SPAN)
    pada = int((moon % NAK_SPAN) // (NAK_SPAN / 4)) + 1

    _, ascmc = swe.houses_ex(jd, latitude, longitude, b"W", _FLAGS)
    lagna_sign = int((ascmc[0] % 360.0) // 30)

    return Chart(
        moon_longitude=moon,
        nakshatra=nak,
        pada=pada,
        rashi=int(moon // 30),
        lagna=lagna_sign,
        planet_longitudes=positions,
        utc=utc,
    )
