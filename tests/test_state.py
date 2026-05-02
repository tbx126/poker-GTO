from engine.actions import Action, ActionKind
from engine.cards import card_from_str
from engine.state import HUState, apply_action, initial_state, legal_actions


def make_state(board=("As", "Kh", "2c"), pot=100, stacks=(1000, 1000)):
    hole = (
        (card_from_str("Qh"), card_from_str("Jh")),
        (card_from_str("9d"), card_from_str("8d")),
    )
    b = tuple(card_from_str(c) for c in board)
    return initial_state(stacks=stacks, pot=pot, hole=hole, board=b)


def test_check_check_advances_street():
    s = make_state()
    s = apply_action(s, Action(ActionKind.CHECK))
    assert s.to_act == 1
    s = apply_action(s, Action(ActionKind.CHECK))
    # street advanced -> committed cleared, to_act back to OOP
    assert s.committed == (0, 0)
    assert s.to_act == 0


def test_bet_call_advances_street_and_pot_grows():
    s = make_state(pot=100)
    actions = legal_actions(s, sizings=(1.0,))
    bet = next(a for a in actions if a.kind == ActionKind.BET and a.amount == 100)
    s = apply_action(s, bet)
    assert s.committed == (100, 0)
    assert s.to_act == 1

    actions = legal_actions(s)
    call = next(a for a in actions if a.kind == ActionKind.CALL)
    s = apply_action(s, call)
    # street settled -> pot = 100 + 100 + 100 = 300, committed cleared
    assert s.pot == 300
    assert s.committed == (0, 0)


def test_fold_terminal():
    s = make_state()
    s = apply_action(s, Action(ActionKind.CHECK))  # OOP check
    actions = legal_actions(s)  # IP to act
    # IP can check or bet; let's bet
    bet = next(a for a in actions if a.kind == ActionKind.BET)
    s = apply_action(s, bet)
    actions = legal_actions(s)
    fold = next(a for a in actions if a.kind == ActionKind.FOLD)
    s = apply_action(s, fold)
    assert s.is_terminal()
    assert s.folded == 0


def test_legal_actions_no_bet_when_facing_bet():
    s = make_state()
    bet = legal_actions(s)[1]  # CHECK is [0], first BET sizing is [1]
    assert bet.kind == ActionKind.BET
    s = apply_action(s, bet)
    actions = legal_actions(s)
    kinds = {a.kind for a in actions}
    assert ActionKind.FOLD in kinds
    assert ActionKind.CALL in kinds
    assert ActionKind.RAISE in kinds
    assert ActionKind.BET not in kinds
    assert ActionKind.CHECK not in kinds


def test_allin_emitted_once():
    s = make_state(stacks=(50, 50), pot=100)
    actions = legal_actions(s, sizings=(0.5, 1.0, 2.0))
    bets = [a for a in actions if a.kind == ActionKind.BET]
    # All sizings either map below stack or to all-in; all-in only once.
    amounts = [a.amount for a in bets]
    assert amounts.count(50) == 1  # exactly one all-in
    assert all(a <= 50 for a in amounts)
