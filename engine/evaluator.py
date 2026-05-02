"""7-card poker hand evaluator over a 52-bit card mask.

`evaluate7(mask)` returns a tuple `(category, *kickers)` that compares
correctly: a > b iff the 5-card hand encoded by `a` beats the one in `b`.
Categories follow the standard high-hand ordering.

Implementation is direct (no lookup tables) — fast enough for solver
tests and exploitability checks. For full-tree CFR over the river we'll
swap in a 2+2-style table later.
"""

from __future__ import annotations

from enum import IntEnum


class HandRank(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    TRIPS = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    QUADS = 7
    STRAIGHT_FLUSH = 8


_SUIT_MASKS = [sum(1 << (r * 4 + s) for r in range(13)) for s in range(4)]
_WHEEL = (1 << 12) | 0b1111  # A + 2,3,4,5 in 13-bit rank space


def _rank_bits_per_suit(mask: int, s: int) -> int:
    bits = mask & _SUIT_MASKS[s]
    out = 0
    for r in range(13):
        if bits & (1 << (r * 4 + s)):
            out |= 1 << r
    return out


def _all_rank_bits(mask: int) -> int:
    out = 0
    for r in range(13):
        if mask & (0xF << (r * 4)):
            out |= 1 << r
    return out


def _rank_counts(mask: int) -> list[int]:
    return [(mask & (0xF << (r * 4))).bit_count() for r in range(13)]


def _straight_high(rank_bits: int) -> int:
    """Highest rank that completes a 5-in-a-row in `rank_bits`, else -1.

    Wheel (A-2-3-4-5) returns 3 (5-high)."""
    for high in range(12, 3, -1):
        run = ((1 << 5) - 1) << (high - 4)
        if (rank_bits & run) == run:
            return high
    if (rank_bits & _WHEEL) == _WHEEL:
        return 3
    return -1


def _top_n(rank_bits: int, n: int) -> list[int]:
    out: list[int] = []
    for r in range(12, -1, -1):
        if rank_bits & (1 << r):
            out.append(r)
            if len(out) == n:
                break
    return out


def evaluate7(mask: int) -> tuple[int, ...]:
    """Score the best 5-card hand from a 7-card bitmask.

    Higher tuple == better hand. Format: (category, kicker1, kicker2, ...).
    """
    if mask.bit_count() != 7:
        raise ValueError(f"expected 7 cards, got {mask.bit_count()}")

    flush_suit = -1
    flush_ranks = 0
    for s in range(4):
        rb = _rank_bits_per_suit(mask, s)
        if rb.bit_count() >= 5:
            flush_suit = s
            flush_ranks = rb
            break

    if flush_suit >= 0:
        sf_high = _straight_high(flush_ranks)
        if sf_high >= 0:
            return (HandRank.STRAIGHT_FLUSH, sf_high)

    counts = _rank_counts(mask)
    quads = [r for r in range(12, -1, -1) if counts[r] == 4]
    trips = [r for r in range(12, -1, -1) if counts[r] == 3]
    pairs = [r for r in range(12, -1, -1) if counts[r] == 2]
    all_ranks = _all_rank_bits(mask)

    if quads:
        q = quads[0]
        kicker = _top_n(all_ranks & ~(1 << q), 1)[0]
        return (HandRank.QUADS, q, kicker)

    if trips and (len(trips) >= 2 or pairs):
        t = trips[0]
        p = trips[1] if len(trips) >= 2 else pairs[0]
        return (HandRank.FULL_HOUSE, t, p)

    if flush_suit >= 0:
        return (HandRank.FLUSH, *_top_n(flush_ranks, 5))

    s_high = _straight_high(all_ranks)
    if s_high >= 0:
        return (HandRank.STRAIGHT, s_high)

    if trips:
        t = trips[0]
        return (HandRank.TRIPS, t, *_top_n(all_ranks & ~(1 << t), 2))

    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        kmask = all_ranks & ~(1 << p1) & ~(1 << p2)
        return (HandRank.TWO_PAIR, p1, p2, _top_n(kmask, 1)[0])

    if pairs:
        p = pairs[0]
        return (HandRank.PAIR, p, *_top_n(all_ranks & ~(1 << p), 3))

    return (HandRank.HIGH_CARD, *_top_n(all_ranks, 5))
