"""Kuhn poker — 3 cards, 2 players, 1-round betting.

Smallest non-trivial imperfect-information game. Used to verify CFR+
correctness — exploitability should drop below ~1e-3 within ~10k iters.

Cards: 0=J, 1=Q, 2=K. Each player antes 1. P1 acts first.
History grammar: '' -> 'p' or 'b'.
  'p'  -> 'pp' (showdown 1) | 'pb' -> 'pbp' (P1 fold, P2 wins 1) | 'pbb' (showdown 2)
  'b'  -> 'bp' (P2 fold, P1 wins 1) | 'bb' (showdown 2)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class KuhnState:
    cards: Optional[tuple[int, int]]  # None before chance deals
    history: str


class KuhnGame:
    num_players = 2

    def initial_state(self) -> KuhnState:
        return KuhnState(cards=None, history="")

    def is_terminal(self, s: KuhnState) -> bool:
        return s.history in ("pp", "bp", "bb", "pbp", "pbb")

    def is_chance(self, s: KuhnState) -> bool:
        return s.cards is None

    def chance_outcomes(self, s: KuhnState) -> list[tuple[tuple[int, int], float]]:
        deck = [(a, b) for a in range(3) for b in range(3) if a != b]
        return [(c, 1.0 / 6.0) for c in deck]

    def apply_chance(self, s: KuhnState, outcome: tuple[int, int]) -> KuhnState:
        return KuhnState(cards=outcome, history="")

    def current_player(self, s: KuhnState) -> int:
        return len(s.history) % 2

    def legal_actions(self, s: KuhnState) -> list[str]:
        return ["p", "b"]

    def apply(self, s: KuhnState, action: str) -> KuhnState:
        return KuhnState(cards=s.cards, history=s.history + action)

    def utility(self, s: KuhnState, player: int) -> float:
        h = s.history
        c1, c2 = s.cards  # type: ignore[misc]
        winner = 0 if c1 > c2 else 1
        if h == "pp":
            return 1.0 if winner == player else -1.0
        if h == "bp":
            return 1.0 if player == 0 else -1.0
        if h == "bb":
            return 2.0 if winner == player else -2.0
        if h == "pbp":
            return 1.0 if player == 1 else -1.0
        if h == "pbb":
            return 2.0 if winner == player else -2.0
        raise ValueError(f"non-terminal: {h}")

    def infoset_key(self, s: KuhnState, player: int) -> str:
        return f"{s.cards[player]}|{s.history}"  # type: ignore[index]
