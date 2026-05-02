from engine.cards import Card, Deck, card_from_str, cards_to_mask, mask_to_cards


def test_card_str_roundtrip():
    for txt in ["2c", "Ah", "Td", "Ks", "5s", "9d"]:
        c = card_from_str(txt)
        assert str(c) == txt


def test_card_index_invariants():
    c = card_from_str("Ah")
    assert c.rank == 12
    assert c.suit == 2  # heart
    assert c.mask == 1 << c.index


def test_mask_roundtrip():
    cards = [card_from_str(t) for t in ["Ah", "Kd", "2c", "Ts", "5s"]]
    m = cards_to_mask(cards)
    assert m.bit_count() == 5
    back = mask_to_cards(m)
    assert sorted(c.index for c in back) == sorted(c.index for c in cards)


def test_duplicate_rejected():
    import pytest

    with pytest.raises(ValueError):
        cards_to_mask([card_from_str("Ah"), card_from_str("Ah")])


def test_deck_deals_unique():
    import random

    rng = random.Random(42)
    d = Deck()
    d.shuffle(rng)
    seen = set()
    for c in d.deal(52):
        assert c.index not in seen
        seen.add(c.index)
    assert d.remaining() == 0
