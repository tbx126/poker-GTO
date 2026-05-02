"""Node-locking on the preflop solver."""

import numpy as np
import pytest

from engine.hand_class import class_index
from solver.preflop import ACTIONS, N, PreflopSolver


def make_lock(history, n_actions, locked_classes_to_probs):
    """Build an (n_actions, 169) lock array with NaN for unlocked classes."""
    arr = np.full((n_actions, N), np.nan)
    for cls_label, probs in locked_classes_to_probs.items():
        idx = class_index(cls_label)
        arr[:, idx] = probs
    return arr


def test_locked_class_strategy_matches_lock_exactly():
    """Lock SB AA to 100% shove; the average strategy must reflect this exactly."""
    h = ()
    n_a = len(ACTIONS[h])
    fold_idx, _, shove_idx = ACTIONS[h].index("fold"), ACTIONS[h].index("open"), ACTIONS[h].index("shove")
    locks = {h: make_lock(h, n_a, {"AA": [0.0, 0.0, 1.0]})}

    solver = PreflopSolver(locks=locks)
    solver.train(20)

    sigma = solver.average_strategy(h)
    aa = class_index("AA")
    assert sigma[shove_idx, aa] == pytest.approx(1.0, abs=1e-9)
    assert sigma[fold_idx, aa] == pytest.approx(0.0, abs=1e-9)


def test_lock_does_not_break_other_classes():
    """Locking one class shouldn't break optimization of other classes."""
    h = ()
    n_a = len(ACTIONS[h])
    locks = {h: make_lock(h, n_a, {"72o": [1.0, 0.0, 0.0]})}  # 72o always folds

    solver = PreflopSolver(locks=locks)
    solver.train(40)

    sigma = solver.average_strategy(h)
    fold_idx = ACTIONS[h].index("fold")
    # 72o forced to 100% fold
    assert sigma[fold_idx, class_index("72o")] == pytest.approx(1.0, abs=1e-9)
    # AA still nearly never folds
    assert sigma[fold_idx, class_index("AA")] < 0.05


def test_mixed_lock_preserved():
    """Mixed lock (e.g., 50/50 open/shove) must be preserved."""
    h = ()
    n_a = len(ACTIONS[h])
    fold_idx = ACTIONS[h].index("fold")
    open_idx = ACTIONS[h].index("open")
    shove_idx = ACTIONS[h].index("shove")
    target = [0.0, 0.5, 0.5]
    locks = {h: make_lock(h, n_a, {"AA": target})}

    solver = PreflopSolver(locks=locks)
    solver.train(20)

    sigma = solver.average_strategy(h)
    aa = class_index("AA")
    assert sigma[fold_idx, aa] == pytest.approx(0.0, abs=1e-9)
    assert sigma[open_idx, aa] == pytest.approx(0.5, abs=1e-9)
    assert sigma[shove_idx, aa] == pytest.approx(0.5, abs=1e-9)


def test_lock_validation_probs_must_sum_to_one():
    h = ()
    n_a = len(ACTIONS[h])
    bad = make_lock(h, n_a, {"AA": [0.4, 0.4, 0.0]})
    with pytest.raises(ValueError, match="sum to 1"):
        PreflopSolver(locks={h: bad})


def test_lock_validation_negative_probs_rejected():
    h = ()
    n_a = len(ACTIONS[h])
    bad = make_lock(h, n_a, {"AA": [-0.1, 0.6, 0.5]})
    with pytest.raises(ValueError, match="non-negative"):
        PreflopSolver(locks={h: bad})


def test_lock_validation_unknown_history_rejected():
    bogus_h = ("imaginary",)
    arr = np.full((2, N), np.nan)
    with pytest.raises(KeyError):
        PreflopSolver(locks={bogus_h: arr})


def test_locking_bb_to_call_changes_sb_response():
    """If BB is forced to call ALL hands vs open, SB should open wider — at minimum,
    SB's open frequency for AA should still be high (sanity), but more relevantly the
    overall opening range should shift looser."""
    h_bb = ("open",)
    n_a_bb = len(ACTIONS[h_bb])
    call_idx = ACTIONS[h_bb].index("call")

    # BB always calls the open with every hand (no fold, no 3bet)
    forced_call = np.zeros(n_a_bb)
    forced_call[call_idx] = 1.0
    lock_all_bb = np.tile(forced_call[:, None], (1, N))
    solver_locked = PreflopSolver(locks={h_bb: lock_all_bb})
    solver_locked.train(60)

    solver_free = PreflopSolver()
    solver_free.train(60)

    fold_idx = ACTIONS[()].index("fold")
    fold_freq_locked = solver_locked.average_strategy(()).sum(axis=1)[fold_idx] / N
    fold_freq_free = solver_free.average_strategy(()).sum(axis=1)[fold_idx] / N
    # When BB always calls, SB's marginal fold-rate should be no higher than baseline
    # (open more, fold less). Allow tiny noise.
    assert fold_freq_locked <= fold_freq_free + 0.02, (
        f"locking BB to call should not increase SB fold rate: {fold_freq_locked} vs {fold_freq_free}"
    )
