"""位棋盘牌表示。

52 张牌编号 0..51，`index = rank * 4 + suit`：
- rank 0..12 = 2..A
- suit 0..3 = c d h s

一手牌用 64 位整数掩码表示——一张牌一位。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable


class Suit(IntEnum):
    CLUB = 0
    DIAMOND = 1
    HEART = 2
    SPADE = 3


class Rank(IntEnum):
    TWO = 0
    THREE = 1
    FOUR = 2
    FIVE = 3
    SIX = 4
    SEVEN = 5
    EIGHT = 6
    NINE = 7
    TEN = 8
    JACK = 9
    QUEEN = 10
    KING = 11
    ACE = 12


RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "cdhs"


@dataclass(frozen=True, order=True)
class Card:
    index: int

    def __post_init__(self) -> None:
        if not 0 <= self.index < 52:
            raise ValueError(f"card index out of range: {self.index}")

    @property
    def rank(self) -> int:
        return self.index >> 2

    @property
    def suit(self) -> int:
        return self.index & 3

    @property
    def mask(self) -> int:
        return 1 << self.index

    def __str__(self) -> str:
        return RANK_CHARS[self.rank] + SUIT_CHARS[self.suit]

    def __repr__(self) -> str:
        return f"Card('{self}')"


def card_from_str(s: str) -> Card:
    if len(s) != 2:
        raise ValueError(f"bad card: {s!r}")
    try:
        r = RANK_CHARS.index(s[0].upper())
        su = SUIT_CHARS.index(s[1].lower())
    except ValueError as e:
        raise ValueError(f"bad card: {s!r}") from e
    return Card(r * 4 + su)


def cards_to_mask(cards: Iterable[Card]) -> int:
    m = 0
    for c in cards:
        b = 1 << c.index
        if m & b:
            raise ValueError(f"duplicate card: {c}")
        m |= b
    return m


def mask_to_cards(mask: int) -> list[Card]:
    out: list[Card] = []
    while mask:
        lsb = mask & -mask
        out.append(Card(lsb.bit_length() - 1))
        mask ^= lsb
    return out


class Deck:
    """52-card deck. Use `shuffle(rng)` then `deal(n)`."""

    def __init__(self) -> None:
        self.cards: list[Card] = [Card(i) for i in range(52)]

    def shuffle(self, rng) -> None:
        rng.shuffle(self.cards)

    def deal(self, n: int) -> list[Card]:
        if n > len(self.cards):
            raise ValueError("deck empty")
        out = self.cards[:n]
        self.cards = self.cards[n:]
        return out

    def remaining(self) -> int:
        return len(self.cards)
