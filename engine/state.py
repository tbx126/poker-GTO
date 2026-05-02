"""Heads-up No-Limit Hold'em postflop state machine.

Postflop only for the MVP — preflop subgame attaches in M2 once the
solver pipeline is stable. State is immutable: `apply` returns a new
state. This makes CFR backtracking trivial.

Conventions:
  - players[0] = OOP (out of position, acts first postflop)
  - players[1] = IP  (in position, acts last)
  - pot       = chips already in the middle (not counting committed-this-street)
  - committed = chips each player has put in *this street*
  - to_call   = max(committed) - committed[player]
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from engine.actions import Action, ActionKind
from engine.cards import Card


@dataclass(frozen=True)
class HUState:
    stacks: tuple[int, int]            # remaining behind for each player
    committed: tuple[int, int]         # chips put in this street (not yet in pot)
    pot: int                           # chips locked from previous streets
    hole: tuple[tuple[Card, Card], tuple[Card, Card]]
    board: tuple[Card, ...]            # 3, 4, or 5 cards
    to_act: int                        # 0 or 1
    last_raise_size: int               # for min-raise rule
    street_aggressor: Optional[int]    # player who made the last bet this street
    history: tuple[Action, ...] = field(default=())
    folded: Optional[int] = None       # if not None, that player folded (terminal)

    @property
    def to_call(self) -> int:
        return self.committed[1 - self.to_act] - self.committed[self.to_act]

    @property
    def total_pot(self) -> int:
        return self.pot + sum(self.committed)

    def is_terminal(self) -> bool:
        if self.folded is not None:
            return True
        # Showdown: all 5 board cards revealed and street is settled
        return len(self.board) == 5 and self._street_settled()

    def _street_settled(self) -> bool:
        """Both players have acted and committed amounts match (or one is all-in)."""
        if not self.history:
            return False
        if self.committed[0] != self.committed[1]:
            return False
        # Need at least one action since the last bet, and both have acted this street.
        # Simple rule: if last action is CHECK and prior was CHECK, settled.
        # If last action is CALL, settled. If only one CHECK so far, not settled.
        last = self.history[-1]
        if last.kind == ActionKind.CALL:
            return True
        if last.kind == ActionKind.CHECK:
            # need two consecutive checks to close street
            return len(self.history) >= 2 and self.history[-2].kind == ActionKind.CHECK
        return False


def initial_state(
    *,
    stacks: tuple[int, int],
    pot: int,
    hole: tuple[tuple[Card, Card], tuple[Card, Card]],
    board: tuple[Card, ...],
) -> HUState:
    if len(board) not in (3, 4, 5):
        raise ValueError("postflop state requires 3-5 board cards")
    return HUState(
        stacks=stacks,
        committed=(0, 0),
        pot=pot,
        hole=hole,
        board=board,
        to_act=0,                # OOP acts first postflop
        last_raise_size=0,
        street_aggressor=None,
        history=(),
    )


def legal_actions(state: HUState, sizings: tuple[float, ...] = (0.5, 1.0)) -> list[Action]:
    """Return legal actions given pot-fraction bet sizings.

    `sizings` are fractions of the pot *after a hypothetical call*. All-in is
    always offered when below the largest sizing's chip cost.
    """
    if state.is_terminal():
        return []

    p = state.to_act
    stack = state.stacks[p]
    to_call = state.to_call
    actions: list[Action] = []

    if to_call == 0:
        actions.append(Action(ActionKind.CHECK))
    else:
        actions.append(Action(ActionKind.FOLD))
        # Call (capped at stack — short-stack call-for-less)
        actions.append(Action(ActionKind.CALL, amount=min(to_call, stack)))

    # Bet / raise sizings — only if player has chips left after a hypothetical call
    chips_after_call = stack - to_call
    if chips_after_call > 0:
        pot_after_call = state.total_pot + to_call
        kind = ActionKind.BET if to_call == 0 else ActionKind.RAISE
        # Min-raise = max(last_raise_size, big-blind) — for postflop MVP we just use last_raise_size.
        min_raise_increment = max(state.last_raise_size, 1)
        seen_amounts: set[int] = set()
        for frac in sizings:
            target_increment = int(round(frac * pot_after_call))
            if target_increment < min_raise_increment:
                target_increment = min_raise_increment
            total = to_call + target_increment
            if total >= stack:
                continue  # this sizing maps onto all-in; emit all-in once below
            if total in seen_amounts:
                continue
            seen_amounts.add(total)
            actions.append(Action(kind, amount=total))
        # All-in
        actions.append(Action(kind, amount=stack))
    return actions


def apply_action(state: HUState, action: Action) -> HUState:
    """Return new state after `action`. Validates kind only — caller must pass a legal action."""
    if state.is_terminal():
        raise ValueError("cannot act on terminal state")

    p = state.to_act
    other = 1 - p
    history = state.history + (action,)

    if action.kind == ActionKind.FOLD:
        return replace(state, history=history, folded=p)

    if action.kind == ActionKind.CHECK:
        new_state = replace(state, history=history, to_act=other)
        if new_state._street_settled():
            return _advance_street(new_state)
        return new_state

    if action.kind == ActionKind.CALL:
        amt = action.amount
        new_committed = list(state.committed)
        new_committed[p] += amt
        new_stacks = list(state.stacks)
        new_stacks[p] -= amt
        new_state = replace(
            state,
            committed=tuple(new_committed),
            stacks=tuple(new_stacks),
            history=history,
            to_act=other,
        )
        if new_state._street_settled():
            return _advance_street(new_state)
        return new_state

    if action.kind in (ActionKind.BET, ActionKind.RAISE):
        amt = action.amount
        new_committed = list(state.committed)
        new_committed[p] += amt
        new_stacks = list(state.stacks)
        new_stacks[p] -= amt
        raise_size = new_committed[p] - state.committed[other]  # increment over previous high
        return replace(
            state,
            committed=tuple(new_committed),
            stacks=tuple(new_stacks),
            history=history,
            to_act=other,
            last_raise_size=raise_size,
            street_aggressor=p,
        )

    raise ValueError(f"unknown action kind: {action.kind}")


def _advance_street(state: HUState) -> HUState:
    """Roll committed chips into pot, clear betting state, OOP to act first."""
    new_pot = state.pot + state.committed[0] + state.committed[1]
    return replace(
        state,
        pot=new_pot,
        committed=(0, 0),
        to_act=0,
        last_raise_size=0,
        street_aggressor=None,
        history=(),  # history is per-street; full action log lives in betting tree
    )
