"""169 hand-class abstraction for No-Limit Hold'em preflop.

Conventions match the design-guide heatmap (rows = first card, cols = second):
  - 13 pairs:   AA, KK, ..., 22         (6 combos each)
  - 78 suited:  AKs, AQs, ..., 32s      (4 combos each)
  - 78 offsuit: AKo, AQo, ..., 32o      (12 combos each)

Sum of combos = 13·6 + 78·4 + 78·12 = 1326 = C(52,2).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from engine.cards import Card, RANK_CHARS

HAND_KIND = Literal["pair", "suited", "offsuit"]


@dataclass(frozen=True)
class HandClass:
    """One of the 169 preflop hand classes (A-2 ranks, suited/offsuit/pair)."""

    label: str          # "AA", "AKs", "AKo"
    kind: HAND_KIND
    high: int           # 0..12, 0 = 2, 12 = A   (NB: low-to-high, NOT heatmap row)
    low: int            # 0..12, low <= high

    @property
    def combos(self) -> int:
        if self.kind == "pair":
            return 6
        if self.kind == "suited":
            return 4
        return 12


def _rank_idx(ch: str) -> int:
    return RANK_CHARS.index(ch)


def hand_class(label: str) -> HandClass:
    """Parse 'AKs' / 'AKo' / 'AA'.

    First char must rank-dominate the second (KAs is not a valid label)."""
    if len(label) == 2 and label[0] == label[1]:
        r = _rank_idx(label[0])
        return HandClass(label=label, kind="pair", high=r, low=r)
    if len(label) == 3:
        h = _rank_idx(label[0])
        l = _rank_idx(label[1])
        if h <= l:
            raise ValueError(f"first rank must be higher: {label!r}")
        if label[2] == "s":
            return HandClass(label=label, kind="suited", high=h, low=l)
        if label[2] == "o":
            return HandClass(label=label, kind="offsuit", high=h, low=l)
    raise ValueError(f"bad hand-class label: {label!r}")


@lru_cache(maxsize=1)
def all_classes() -> tuple[HandClass, ...]:
    out: list[HandClass] = []
    for r in range(12, -1, -1):
        out.append(HandClass(label=f"{RANK_CHARS[r]}{RANK_CHARS[r]}", kind="pair", high=r, low=r))
    for h in range(12, -1, -1):
        for l in range(h - 1, -1, -1):
            hi, lo = RANK_CHARS[h], RANK_CHARS[l]
            out.append(HandClass(label=f"{hi}{lo}s", kind="suited", high=h, low=l))
            out.append(HandClass(label=f"{hi}{lo}o", kind="offsuit", high=h, low=l))
    return tuple(out)


@lru_cache(maxsize=None)
def class_index(label: str) -> int:
    for i, c in enumerate(all_classes()):
        if c.label == label:
            return i
    raise KeyError(label)


@lru_cache(maxsize=None)
def class_combos(label: str) -> tuple[tuple[Card, Card], ...]:
    """Concrete card pairs that realize this class.

    Pairs: 6 combos. Suited: 4 combos. Offsuit: 12 combos."""
    cls = hand_class(label)
    out: list[tuple[Card, Card]] = []
    if cls.kind == "pair":
        for s1 in range(4):
            for s2 in range(s1 + 1, 4):
                out.append((Card(cls.high * 4 + s1), Card(cls.high * 4 + s2)))
    elif cls.kind == "suited":
        for s in range(4):
            out.append((Card(cls.high * 4 + s), Card(cls.low * 4 + s)))
    else:  # offsuit
        for s1 in range(4):
            for s2 in range(4):
                if s1 != s2:
                    out.append((Card(cls.high * 4 + s1), Card(cls.low * 4 + s2)))
    return tuple(out)


def combo_to_class_label(c1: Card, c2: Card) -> str:
    """Map a specific 2-card combo back to its 169-class label."""
    if c1.rank == c2.rank:
        return f"{RANK_CHARS[c1.rank]}{RANK_CHARS[c1.rank]}"
    hi, lo = (c1, c2) if c1.rank > c2.rank else (c2, c1)
    suffix = "s" if hi.suit == lo.suit else "o"
    return f"{RANK_CHARS[hi.rank]}{RANK_CHARS[lo.rank]}{suffix}"


def class_probability(label: str) -> float:
    """Marginal probability a uniformly-dealt 2-card hand is this class."""
    return hand_class(label).combos / 1326.0


# Sanity check at import time — cheap and catches indexing bugs early.
_classes = all_classes()
assert len(_classes) == 169, "169-class invariant"
assert sum(c.combos for c in _classes) == 1326, "combo count invariant"
