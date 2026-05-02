from engine.hand_class import (
    all_classes,
    class_combos,
    class_index,
    class_probability,
    combo_to_class_label,
    hand_class,
)
from engine.cards import card_from_str


def test_169_classes():
    cls = all_classes()
    assert len(cls) == 169
    assert sum(c.combos for c in cls) == 1326


def test_pair_class():
    c = hand_class("AA")
    assert c.kind == "pair"
    assert c.combos == 6
    assert len(class_combos("AA")) == 6
    # All 6 unordered pairs of the 4 aces
    assert {(a.index, b.index) for a, b in class_combos("AA")} == {
        (a.index, b.index)
        for a in [card_from_str(f"A{s}") for s in "cdhs"]
        for b in [card_from_str(f"A{s}") for s in "cdhs"]
        if a.index < b.index
    }


def test_suited_class():
    c = hand_class("AKs")
    assert c.kind == "suited"
    assert c.combos == 4
    combos = class_combos("AKs")
    assert len(combos) == 4
    for a, b in combos:
        assert a.rank == 12 and b.rank == 11
        assert a.suit == b.suit  # suited


def test_offsuit_class():
    c = hand_class("AKo")
    assert c.kind == "offsuit"
    assert c.combos == 12
    combos = class_combos("AKo")
    assert len(combos) == 12
    for a, b in combos:
        assert a.rank == 12 and b.rank == 11
        assert a.suit != b.suit


def test_combo_round_trip():
    # Pick concrete combos and verify they map back
    for txt, expected in [
        ("AhAd", "AA"),
        ("AhKh", "AKs"),
        ("AhKd", "AKo"),
        ("2c2d", "22"),
        ("Ts9s", "T9s"),
        ("Td9c", "T9o"),
    ]:
        c1 = card_from_str(txt[:2])
        c2 = card_from_str(txt[2:])
        assert combo_to_class_label(c1, c2) == expected


def test_probabilities_sum_to_one():
    p = sum(class_probability(c.label) for c in all_classes())
    assert abs(p - 1.0) < 1e-12


def test_class_indices_unique():
    seen = set()
    for c in all_classes():
        i = class_index(c.label)
        assert i not in seen
        seen.add(i)
    assert seen == set(range(169))


def test_label_validation():
    import pytest

    with pytest.raises(ValueError):
        hand_class("KAs")  # wrong order
    with pytest.raises(ValueError):
        hand_class("AKx")  # bad suffix
    with pytest.raises(ValueError):
        hand_class("Z2s")  # bad rank
