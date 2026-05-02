"""Action types for No-Limit Hold'em.

Bet sizes are stored as absolute chip totals — the *amount this player
puts in beyond what they've already committed this street*. Sizing
ladders (1/3 pot, 2/3 pot, pot, all-in) live in the solver tree-builder,
not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionKind(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    amount: int = 0  # chips added this turn; 0 for fold/check, call-amount for call

    def __str__(self) -> str:
        if self.kind in (ActionKind.FOLD, ActionKind.CHECK):
            return self.kind.value
        return f"{self.kind.value}({self.amount})"


FOLD = Action(ActionKind.FOLD)
CHECK = Action(ActionKind.CHECK)
