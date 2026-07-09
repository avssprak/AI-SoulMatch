"""Ashta Koota (Guna Milan) compatibility scoring — 36 points total.

All lookups follow the standard published tables used in North-Indian style
guna milan. Nakshatra indexes are 0-26 (Ashwini=0), rashi indexes 0-11
(Mesha=0), matching soulmatch.astrology.ephemeris.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- static tables -----------------------------------------------------------

# Varna by moon rashi; ranks: Brahmin 4 > Kshatriya 3 > Vaishya 2 > Shudra 1
_VARNA_BY_RASHI = [3, 2, 1, 4, 3, 2, 1, 4, 3, 2, 1, 4]
_VARNA_NAMES = {4: "Brahmin", 3: "Kshatriya", 2: "Vaishya", 1: "Shudra"}

# Vashya groups
CHATUSHPADA, MANAVA, JALACHARA, VANACHARA, KEETA = range(5)
_VASHYA_NAMES = ["Chatushpada", "Manava", "Jalachara", "Vanachara", "Keeta"]
# score[boy_group][girl_group]
_VASHYA_SCORE = [
    [2.0, 1.0, 1.0, 0.0, 1.0],
    [1.0, 2.0, 0.5, 0.0, 1.0],
    [1.0, 1.0, 2.0, 0.0, 1.0],
    [0.0, 0.0, 0.0, 2.0, 0.0],
    [1.0, 1.0, 1.0, 0.0, 2.0],
]

# Yoni animal per nakshatra (0-26)
_YONI_ANIMALS = [
    "Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep",
    "Cat", "Rat", "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger",
    "Deer", "Deer", "Dog", "Monkey", "Mongoose", "Monkey", "Lion", "Horse",
    "Lion", "Cow", "Elephant",
]
_YONI_ORDER = [
    "Horse", "Elephant", "Sheep", "Serpent", "Dog", "Cat", "Rat", "Cow",
    "Buffalo", "Tiger", "Deer", "Monkey", "Mongoose", "Lion",
]
# Symmetric 14x14 compatibility matrix (standard published values)
_YONI_MATRIX = [
    [4, 2, 2, 3, 2, 2, 2, 1, 0, 1, 3, 3, 2, 1],
    [2, 4, 3, 3, 2, 2, 2, 2, 3, 1, 2, 3, 2, 0],
    [2, 3, 4, 2, 1, 2, 1, 3, 3, 1, 2, 0, 3, 1],
    [3, 3, 2, 4, 2, 1, 1, 1, 1, 2, 2, 2, 0, 2],
    [2, 2, 1, 2, 4, 2, 1, 2, 2, 1, 0, 2, 1, 1],
    [2, 2, 2, 1, 2, 4, 0, 2, 2, 1, 3, 3, 2, 1],
    [2, 2, 1, 1, 1, 0, 4, 2, 2, 2, 2, 2, 1, 2],
    [1, 2, 3, 1, 2, 2, 2, 4, 3, 0, 3, 2, 2, 1],
    [0, 3, 3, 1, 2, 2, 2, 3, 4, 1, 2, 2, 2, 1],
    [1, 1, 1, 2, 1, 1, 2, 0, 1, 4, 1, 1, 2, 1],
    [3, 2, 2, 2, 0, 3, 2, 3, 2, 1, 4, 3, 2, 1],
    [3, 3, 0, 2, 2, 3, 2, 2, 2, 1, 3, 4, 3, 2],
    [2, 2, 3, 0, 1, 2, 1, 2, 2, 2, 2, 3, 4, 2],
    [1, 0, 1, 2, 1, 1, 2, 1, 1, 1, 1, 2, 2, 4],
]

# Rashi lords
_RASHI_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
]
# Natural planetary friendships
_FRIENDS = {
    "Sun": {"Moon", "Mars", "Jupiter"},
    "Moon": {"Sun", "Mercury"},
    "Mars": {"Sun", "Moon", "Jupiter"},
    "Mercury": {"Sun", "Venus"},
    "Jupiter": {"Sun", "Moon", "Mars"},
    "Venus": {"Mercury", "Saturn"},
    "Saturn": {"Mercury", "Venus"},
}
_ENEMIES = {
    "Sun": {"Venus", "Saturn"},
    "Moon": set(),
    "Mars": {"Mercury"},
    "Mercury": {"Moon"},
    "Jupiter": {"Mercury", "Venus"},
    "Venus": {"Sun", "Moon"},
    "Saturn": {"Sun", "Moon", "Mars"},
}

# Gana per nakshatra: 0 Deva, 1 Manushya, 2 Rakshasa
_GANA = [
    0, 1, 2, 1, 0, 1, 0, 0, 2, 2, 1, 1, 0, 2,
    0, 2, 0, 2, 2, 1, 1, 0, 2, 2, 1, 1, 0,
]
_GANA_NAMES = ["Deva", "Manushya", "Rakshasa"]
# score[boy_gana][girl_gana]
_GANA_SCORE = [
    [6, 6, 1],
    [5, 6, 0],
    [1, 0, 6],
]

# Nadi per nakshatra: zigzag Adi/Madhya/Antya pattern repeating every 9
_NADI_CYCLE = [0, 1, 2, 2, 1, 0, 0, 1, 2]
_NADI_NAMES = ["Adi", "Madhya", "Antya"]

_TARA_NAMES = [
    "Janma", "Sampat", "Vipat", "Kshema", "Pratyari",
    "Sadhaka", "Naidhana", "Mitra", "Parama Mitra",
]
_BAD_TARAS = {2, 4, 6}  # Vipat, Pratyari, Naidhana (0-indexed)


# --- helpers -----------------------------------------------------------------

def vashya_group(rashi: int, moon_longitude: float) -> int:
    """Vashya classification; Dhanu and Makara split at 15° within the sign."""
    deg_in_sign = moon_longitude % 30
    if rashi in (0, 1):
        return CHATUSHPADA
    if rashi in (2, 5, 6, 10):
        return MANAVA
    if rashi in (3, 11):
        return JALACHARA
    if rashi == 4:
        return VANACHARA
    if rashi == 7:
        return KEETA
    if rashi == 8:  # Dhanu
        return MANAVA if deg_in_sign < 15 else CHATUSHPADA
    # rashi == 9, Makara
    return CHATUSHPADA if deg_in_sign < 15 else JALACHARA


def nadi_of(nakshatra: int) -> int:
    return _NADI_CYCLE[nakshatra % 9]


def _tara_index(from_nak: int, to_nak: int) -> int:
    count = ((to_nak - from_nak) % 27) + 1
    return (count - 1) % 9


def _maitri_relation(lord_a: str, lord_b: str) -> str:
    if lord_a == lord_b or lord_b in _FRIENDS[lord_a]:
        return "friend"
    if lord_b in _ENEMIES[lord_a]:
        return "enemy"
    return "neutral"


# --- main scoring ------------------------------------------------------------

@dataclass
class PersonInput:
    nakshatra: int          # 0-26
    rashi: int              # 0-11
    moon_longitude: float   # needed for half-sign vashya; rashi*30+15 if unknown


def ashta_koota(groom: PersonInput, bride: PersonInput) -> dict:
    """Return the 8 koota scores plus total and interpretation."""
    result: dict = {"kootas": {}}
    k = result["kootas"]

    # 1. Varna (1)
    gv, bv = _VARNA_BY_RASHI[groom.rashi], _VARNA_BY_RASHI[bride.rashi]
    k["Varna"] = {
        "score": 1.0 if gv >= bv else 0.0, "max": 1,
        "detail": f"Groom {_VARNA_NAMES[gv]}, Bride {_VARNA_NAMES[bv]}",
    }

    # 2. Vashya (2)
    gg = vashya_group(groom.rashi, groom.moon_longitude)
    bg = vashya_group(bride.rashi, bride.moon_longitude)
    k["Vashya"] = {
        "score": _VASHYA_SCORE[gg][bg], "max": 2,
        "detail": f"Groom {_VASHYA_NAMES[gg]}, Bride {_VASHYA_NAMES[bg]}",
    }

    # 3. Tara (3) — counted both directions, 1.5 each if auspicious
    t_bg = _tara_index(bride.nakshatra, groom.nakshatra)
    t_gb = _tara_index(groom.nakshatra, bride.nakshatra)
    tara = (0.0 if t_bg in _BAD_TARAS else 1.5) + (0.0 if t_gb in _BAD_TARAS else 1.5)
    k["Tara"] = {
        "score": tara, "max": 3,
        "detail": f"Bride→Groom {_TARA_NAMES[t_bg]}, Groom→Bride {_TARA_NAMES[t_gb]}",
    }

    # 4. Yoni (4)
    ga = _YONI_ANIMALS[groom.nakshatra]
    ba = _YONI_ANIMALS[bride.nakshatra]
    yoni = _YONI_MATRIX[_YONI_ORDER.index(ga)][_YONI_ORDER.index(ba)]
    k["Yoni"] = {"score": float(yoni), "max": 4, "detail": f"Groom {ga}, Bride {ba}"}

    # 5. Graha Maitri (5)
    gl, bl = _RASHI_LORDS[groom.rashi], _RASHI_LORDS[bride.rashi]
    rel_gb, rel_bg = _maitri_relation(gl, bl), _maitri_relation(bl, gl)
    rels = {rel_gb, rel_bg}
    if rels == {"friend"}:
        maitri = 5.0
    elif rels == {"friend", "neutral"}:
        maitri = 4.0
    elif rels == {"neutral"}:
        maitri = 3.0
    elif rels == {"friend", "enemy"}:
        maitri = 1.0
    elif rels == {"neutral", "enemy"}:
        maitri = 0.5
    else:
        maitri = 0.0
    k["Graha Maitri"] = {
        "score": maitri, "max": 5,
        "detail": f"Lords {gl} & {bl}: {rel_gb}/{rel_bg}",
    }

    # 6. Gana (6)
    ggn, bgn = _GANA[groom.nakshatra], _GANA[bride.nakshatra]
    k["Gana"] = {
        "score": float(_GANA_SCORE[ggn][bgn]), "max": 6,
        "detail": f"Groom {_GANA_NAMES[ggn]}, Bride {_GANA_NAMES[bgn]}",
    }

    # 7. Bhakoot (7) — 2/12, 5/9, 6/8 sign pairs are inauspicious
    dist = (groom.rashi - bride.rashi) % 12
    bad_bhakoot = dist in (1, 11, 4, 8, 5, 7)
    k["Bhakoot"] = {
        "score": 0.0 if bad_bhakoot else 7.0, "max": 7,
        "detail": f"Sign distance {dist + 1}/{(12 - dist) % 12 + 1}"
                  + (" — dosha" if bad_bhakoot else ""),
    }

    # 8. Nadi (8) — same nadi is the strongest dosha
    gn, bn = nadi_of(groom.nakshatra), nadi_of(bride.nakshatra)
    k["Nadi"] = {
        "score": 0.0 if gn == bn else 8.0, "max": 8,
        "detail": f"Groom {_NADI_NAMES[gn]}, Bride {_NADI_NAMES[bn]}"
                  + (" — Nadi dosha" if gn == bn else ""),
    }

    total = sum(v["score"] for v in k.values())
    result["total"] = total
    result["max"] = 36
    if total < 18:
        verdict = "Not recommended"
    elif total < 25:
        verdict = "Average"
    elif total < 33:
        verdict = "Good"
    else:
        verdict = "Excellent"
    result["verdict"] = verdict
    return result
