"""HU preflop CFR+ — convergence + sane strategies on real equity table."""

import numpy as np
import pytest

from engine.hand_class import class_index
from solver.preflop import (
    ACTIONS,
    PreflopSolver,
    class_probability_vector,
)


@pytest.fixture(scope="module")
def trained() -> PreflopSolver:
    s = PreflopSolver()
    s.train(50)
    return s


def test_class_probabilities_sum_to_one():
    p = class_probability_vector()
    assert abs(p.sum() - 1.0) < 1e-12


def test_strategies_have_expected_shapes(trained):
    sb_open = trained.average_strategy(())
    bb_vs_open = trained.average_strategy(("open",))
    sb_vs_3bet = trained.average_strategy(("open", "3bet"))
    bb_vs_4bet = trained.average_strategy(("open", "3bet", "4bet"))
    bb_vs_shove = trained.average_strategy(("shove",))

    assert sb_open.shape == (3, 169)        # fold | open | shove
    assert bb_vs_open.shape == (3, 169)     # fold | call | 3bet
    assert sb_vs_3bet.shape == (3, 169)
    assert bb_vs_4bet.shape == (2, 169)
    assert bb_vs_shove.shape == (2, 169)


def test_strategies_sum_to_one_per_class(trained):
    for h in ACTIONS:
        sigma = trained.average_strategy(h)
        col_sums = sigma.sum(axis=0)
        assert np.allclose(col_sums, 1.0, atol=1e-9), f"history {h} normalisation"


def test_aa_never_folds_preflop(trained):
    """SB with AA must never fold."""
    sigma = trained.average_strategy(())
    fold_idx = ACTIONS[()].index("fold")
    aa = class_index("AA")
    assert sigma[fold_idx, aa] < 0.02, f"AA folds at {sigma[fold_idx, aa]:.3f}"


def test_72o_doesnt_shove_blindly(trained):
    """72o: shove freq should be below 30% (it's the worst hand)."""
    sigma = trained.average_strategy(())
    shove_idx = ACTIONS[()].index("shove")
    weak = class_index("72o")
    assert sigma[shove_idx, weak] < 0.3, f"72o shoves at {sigma[shove_idx, weak]:.3f}"


def test_aa_calls_or_4bets_against_3bet(trained):
    """SB with AA facing 3bet must not fold."""
    sigma = trained.average_strategy(("open", "3bet"))
    fold_idx = ACTIONS[("open", "3bet")].index("fold")
    aa = class_index("AA")
    assert sigma[fold_idx, aa] < 0.05, f"AA folds to 3bet at {sigma[fold_idx, aa]:.3f}"


def test_bb_calls_with_aa_vs_shove(trained):
    """BB with AA must call SB shove."""
    sigma = trained.average_strategy(("shove",))
    call_idx = ACTIONS[("shove",)].index("call")
    aa = class_index("AA")
    assert sigma[call_idx, aa] > 0.95, f"AA calls shove at {sigma[call_idx, aa]:.3f}"


def test_exploitability_decreases():
    """Train in two chunks; exploitability must drop."""
    s = PreflopSolver()
    s.train(20)
    eps0 = s.exploitability()
    s.train(40)
    eps1 = s.exploitability()
    assert eps1 < eps0, f"exploitability did not improve: {eps0} -> {eps1}"
    # End-state sanity: must be < 5 chips (game value scale ~1bb per hand)
    assert eps1 < 5.0, f"final exploitability {eps1} too large"


def test_open_range_decreases_with_hand_strength(trained):
    """Loose monotonicity — strong hands open more often than offsuit junk.
    Allowed deviations because 50 iters isn't fully converged."""
    sigma = trained.average_strategy(())
    fold_idx = ACTIONS[()].index("fold")

    aa_fold = sigma[fold_idx, class_index("AA")]
    junk_fold = sigma[fold_idx, class_index("72o")]

    assert aa_fold < junk_fold, f"AA fold {aa_fold} >= 72o fold {junk_fold}"
