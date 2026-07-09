"""Offline place-name -> (lat, lon, timezone) resolution.

Uses geonamescache (cities with population > 15k, bundled data) plus
timezonefinder as a fallback when a city record lacks a timezone. No network
calls, no API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Place:
    name: str
    country: str
    latitude: float
    longitude: float
    timezone: str


@lru_cache(maxsize=1)
def _cities() -> list[dict]:
    import geonamescache

    gc = geonamescache.GeonamesCache()
    return list(gc.get_cities().values())


def _tz_for(lat: float, lon: float) -> str | None:
    from timezonefinder import TimezoneFinder

    return TimezoneFinder().timezone_at(lat=lat, lng=lon)


def lookup(place_name: str, country_hint: str | None = "IN") -> Place | None:
    """Best match by name; prefers the country hint, then largest population."""
    query = place_name.strip().lower()
    if not query:
        return None

    exact, prefix = [], []
    for city in _cities():
        names = [city["name"].lower()] + [a.lower() for a in city.get("alternatenames", [])[:20]]
        if query in names:
            exact.append(city)
        elif any(n.startswith(query) for n in names[:1]):
            prefix.append(city)

    candidates = exact or prefix
    if not candidates:
        return None

    def rank(c: dict) -> tuple:
        return (c["countrycode"] == country_hint, c.get("population", 0))

    best = max(candidates, key=rank)
    tz = best.get("timezone") or _tz_for(best["latitude"], best["longitude"])
    if not tz:
        return None
    return Place(
        name=best["name"],
        country=best["countrycode"],
        latitude=float(best["latitude"]),
        longitude=float(best["longitude"]),
        timezone=tz,
    )
