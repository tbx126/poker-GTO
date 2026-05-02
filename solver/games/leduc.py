"""Leduc Hold'em — 6-card, 2-round limit poker.

Standard rules:
  - Deck: 2 each of J(0), Q(1), K(2). Suits irrelevant; we track ranks only.
  - Both players ante 1.
  - Round 1: each dealt 1 private card; betting (bet size 2, max 2 raises).
  - Public card dealt from remaining 4.
  - Round 2: betting (bet size 4, max 2 raises).
  - Showdown: a private card matching the public rank = pair (wins). Else
    high card. Tie if both private ranks equal and neither matches public.

Action grammar per round (c=check/call, r=bet/raise, f=fold):
  ''     -> 'c' | 'r'                     'crr' -> 'c' | 'f'
  'c'    -> 'c' (close) | 'r'             'r'   -> 'c' (close) | 'r' | 'f'
  'cr'   -> 'c' | 'r' | 'f'               'rr'  -> 'c' (close) | 'f'   (cap = 2 raises)

State stores ranks only (rank-aggregated chance reduces 30→9 private and 4→2-3
public branches, ~5× speedup vs. a card-index enumeration).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


_NUM_RANKS = 3
_COPIES_PER_RANK = 2  # 2 of each rank in the 6-card deck
_DECK_SIZE = _NUM_RANKS * _COPIES_PER_RANK
_BET_SIZE_R1 = 2
_BET_SIZE_R2 = 4

_ROUND_CLOSED = {"cc", "rc", "rrc", "crc", "crrc"}
_ROUND_FOLD = {"rf", "rrf", "crf", "crrf"}


def _round_status(actions: str) -> Optional[str]:
    if actions in _ROUND_CLOSED:
        return "closed"
    if actions in _ROUND_FOLD:
        return "fold"
    return None


def _round_commit(actions: str, bet_size: int) -> tuple[int, int]:
    """Chips put in *this round* by (p1, p2). P1 acts first."""
    p1, p2 = 0, 0
    cur = 0
    for a in actions:
        high = max(p1, p2)
        if a == "c":
            if high > 0:
                if cur == 0:
                    p1 = high
                else:
                    p2 = high
        elif a == "r":
            new_amt = high + bet_size
            if cur == 0:
                p1 = new_amt
            else:
                p2 = new_amt
        cur = 1 - cur
    return p1, p2


def _folder_from_actions(actions: str) -> Optional[int]:
    if actions and actions[-1] == "f":
        return (len(actions) - 1) % 2  # P1 acts first; len-1 = whose turn it was
    return None


@dataclass(frozen=True)
class LeducState:
    p1_rank: Optional[int]
    p2_rank: Optional[int]
    public_rank: Optional[int]
    round1: str = ""
    round2: str = ""


class LeducGame:
    num_players = 2

    def initial_state(self) -> LeducState:
        return LeducState(None, None, None)

    # ----- chance -----

    def is_chance(self, s: LeducState) -> bool:
        if s.p1_rank is None:
            return True
        if s.public_rank is None and _round_status(s.round1) == "closed":
            return True
        return False

    def chance_outcomes(self, s: LeducState):
        if s.p1_rank is None:
            outs = []
            total = _DECK_SIZE * (_DECK_SIZE - 1)  # 30 ordered card-index pairs
            for r1 in range(_NUM_RANKS):
                for r2 in range(_NUM_RANKS):
                    if r1 == r2:
                        # both come from rank with 2 copies: 2*1 = 2 ordered draws
                        ways = _COPIES_PER_RANK * (_COPIES_PER_RANK - 1)
                    else:
                        # 2 copies of r1 × 2 copies of r2
                        ways = _COPIES_PER_RANK * _COPIES_PER_RANK
                    outs.append(((r1, r2), ways / total))
            return outs

        # Public: aggregate remaining cards by rank
        remaining = [_COPIES_PER_RANK] * _NUM_RANKS
        remaining[s.p1_rank] -= 1
        remaining[s.p2_rank] -= 1
        total_left = sum(remaining)
        return [(r, count / total_left) for r, count in enumerate(remaining) if count > 0]

    def apply_chance(self, s: LeducState, outcome) -> LeducState:
        if s.p1_rank is None:
            r1, r2 = outcome
            return replace(s, p1_rank=r1, p2_rank=r2)
        return replace(s, public_rank=outcome)

    # ----- terminal & utility -----

    def is_terminal(self, s: LeducState) -> bool:
        if _folder_from_actions(s.round1) is not None:
            return True
        if _folder_from_actions(s.round2) is not None:
            return True
        if s.public_rank is not None and _round_status(s.round2) == "closed":
            return True
        return False

    def utility(self, s: LeducState, player: int) -> float:
        p1_r1, p2_r1 = _round_commit(s.round1, _BET_SIZE_R1)
        p1_r2, p2_r2 = _round_commit(s.round2, _BET_SIZE_R2)
        p1_total = 1 + p1_r1 + p1_r2
        p2_total = 1 + p2_r1 + p2_r2
        pot = p1_total + p2_total

        folded = _folder_from_actions(s.round1)
        if folded is None:
            folded = _folder_from_actions(s.round2)

        if folded is not None:
            winner: Optional[int] = 1 - folded
        else:
            winner = self._showdown_winner(s.p1_rank, s.p2_rank, s.public_rank)

        contributed = p1_total if player == 0 else p2_total
        if winner is None:
            return 0.0
        if winner == player:
            return float(pot - contributed)
        return float(-contributed)

    @staticmethod
    def _showdown_winner(r1, r2, rp) -> Optional[int]:
        if r1 == rp:
            return 0
        if r2 == rp:
            return 1
        if r1 > r2:
            return 0
        if r2 > r1:
            return 1
        return None

    # ----- decision nodes -----

    def _current_round_actions(self, s: LeducState) -> str:
        return s.round1 if s.public_rank is None else s.round2

    def current_player(self, s: LeducState) -> int:
        return len(self._current_round_actions(s)) % 2

    def legal_actions(self, s: LeducState) -> list[str]:
        a = self._current_round_actions(s)
        if a == "" or a == "c":
            return ["c", "r"]
        if a == "r" or a == "cr":
            return ["c", "r", "f"]
        if a == "rr" or a == "crr":
            return ["c", "f"]
        raise ValueError(f"unexpected round-action state: {a!r}")

    def apply(self, s: LeducState, action: str) -> LeducState:
        if s.public_rank is None:
            return replace(s, round1=s.round1 + action)
        return replace(s, round2=s.round2 + action)

    def infoset_key(self, s: LeducState, player: int) -> str:
        my_rank = s.p1_rank if player == 0 else s.p2_rank
        if s.public_rank is None:
            return f"r1|{my_rank}|{s.round1}"
        return f"r2|{my_rank}|{s.public_rank}|{s.round1}|{s.round2}"
