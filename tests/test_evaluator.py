"""Hand evaluator correctness — categories, kickers, ordering, edge cases."""

import itertools
import random

from engine.cards import Card, card_from_str, cards_to_mask
from engine.evaluator import HandRank, evaluate7


def hand(*cards: str) -> int:
    return cards_to_mask([card_from_str(c) for c in cards])


def cat(score: tuple[int, ...]) -> int:
    return score[0]


def test_royal_flush():
    s = evaluate7(hand("As", "Ks", "Qs", "Js", "Ts", "2c", "3d"))
    assert cat(s) == HandRank.STRAIGHT_FLUSH
    assert s[1] == 12  # ace high


def test_steel_wheel():
    s = evaluate7(hand("Ah", "2h", "3h", "4h", "5h", "Kc", "Qd"))
    assert cat(s) == HandRank.STRAIGHT_FLUSH
    assert s[1] == 3  # 5-high


def test_quads_kicker():
    s = evaluate7(hand("Ah", "Ad", "Ac", "As", "Kd", "2c", "3s"))
    assert cat(s) == HandRank.QUADS
    assert s == (HandRank.QUADS, 12, 11)


def test_full_house_two_trips():
    # AAA KKK Q -> AAA over KK
    s = evaluate7(hand("Ah", "Ad", "Ac", "Kh", "Kd", "Kc", "Qs"))
    assert s == (HandRank.FULL_HOUSE, 12, 11)


def test_full_house_trips_pair():
    s = evaluate7(hand("9h", "9d", "9c", "5h", "5d", "Kc", "2s"))
    assert s == (HandRank.FULL_HOUSE, 7, 3)


def test_flush_picks_top_five():
    s = evaluate7(hand("2h", "5h", "7h", "9h", "Jh", "Kh", "Ad"))
    assert cat(s) == HandRank.FLUSH
    # Top 5 hearts: K J 9 7 5 -> ranks 11 9 7 5 3
    assert s[1:] == (11, 9, 7, 5, 3)


def test_straight_wheel():
    s = evaluate7(hand("Ah", "2d", "3c", "4s", "5h", "Kd", "Qc"))
    assert s == (HandRank.STRAIGHT, 3)


def test_straight_broadway():
    s = evaluate7(hand("Ah", "Kd", "Qc", "Js", "Th", "2d", "3c"))
    assert s == (HandRank.STRAIGHT, 12)


def test_trips_kickers():
    s = evaluate7(hand("Kh", "Kd", "Kc", "Ah", "5d", "2c", "3s"))
    assert s == (HandRank.TRIPS, 11, 12, 3)


def test_two_pair_three_pairs_picks_top_two():
    # AA KK QQ 9 -> AA-KK with Q kicker
    s = evaluate7(hand("Ah", "Ad", "Kh", "Kd", "Qh", "Qd", "9c"))
    assert s == (HandRank.TWO_PAIR, 12, 11, 10)


def test_pair_three_kickers():
    s = evaluate7(hand("9h", "9d", "Ah", "Kd", "Qc", "2s", "3s"))
    assert s == (HandRank.PAIR, 7, 12, 11, 10)


def test_high_card_top_five():
    s = evaluate7(hand("Ah", "Kd", "Qc", "Js", "9h", "7d", "2c"))
    assert s == (HandRank.HIGH_CARD, 12, 11, 10, 9, 7)


def test_ordering_quads_beat_full_house():
    quads = evaluate7(hand("2h", "2d", "2c", "2s", "3d", "5c", "7s"))
    fh = evaluate7(hand("Ah", "Ad", "Ac", "Kh", "Kd", "5c", "7s"))
    assert quads > fh


def test_ordering_flush_beats_straight():
    flush = evaluate7(hand("2h", "5h", "7h", "9h", "Jh", "3d", "4c"))
    straight = evaluate7(hand("9d", "Tc", "Js", "Qh", "Kd", "2c", "3c"))
    assert flush > straight


def test_higher_pair_beats_lower_pair():
    higher = evaluate7(hand("Ah", "Ad", "5c", "7s", "9h", "2d", "3c"))
    lower = evaluate7(hand("Kh", "Kd", "5c", "7s", "9h", "2d", "3c"))
    assert higher > lower


def test_pair_kicker_decides():
    a = evaluate7(hand("Ah", "Ad", "Kc", "7s", "9h", "2d", "3c"))
    b = evaluate7(hand("Ah", "Ad", "Qc", "7s", "9h", "2d", "3c"))
    assert a > b


def test_random_hands_smoke():
    """Just shouldn't crash on a wide sample of legal 7-card hands."""
    rng = random.Random(0)
    for _ in range(2000):
        idx = rng.sample(range(52), 7)
        m = sum(1 << i for i in idx)
        score = evaluate7(m)
        assert 0 <= score[0] <= 8
