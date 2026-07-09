from soulmatch.astrology.koota import PersonInput, ashta_koota, nadi_of, vashya_group


def test_identical_nakshatra_scores_max_or_near_max():
    """Same nakshatra & rashi: varna/vashya/yoni/maitri/gana all trivially match;
    nadi will be identical (dosha), so total should be 28 (36 - 8 nadi)."""
    person = PersonInput(nakshatra=3, rashi=1, moon_longitude=1 * 30 + 15)  # Rohini, Vrishabha
    result = ashta_koota(person, person)
    assert result["kootas"]["Nadi"]["score"] == 0.0
    assert result["kootas"]["Varna"]["score"] == 1.0
    assert result["kootas"]["Yoni"]["score"] == 4.0
    assert result["total"] == 28.0


def test_total_never_exceeds_36():
    for gn in range(0, 27, 3):
        for bn in range(0, 27, 3):
            groom = PersonInput(gn, (gn * 30 // 30) % 12, (gn % 12) * 30 + 10)
            bride = PersonInput(bn, (bn * 30 // 30) % 12, (bn % 12) * 30 + 10)
            result = ashta_koota(groom, bride)
            assert 0 <= result["total"] <= 36


def test_nadi_cycle_length_and_range():
    values = {nadi_of(n) for n in range(27)}
    assert values == {0, 1, 2}


def test_vashya_group_dhanu_split():
    # Dhanu = rashi index 8; first half Manava, second half Chatushpada
    from soulmatch.astrology.koota import CHATUSHPADA, MANAVA
    assert vashya_group(8, 8 * 30 + 5) == MANAVA
    assert vashya_group(8, 8 * 30 + 25) == CHATUSHPADA
