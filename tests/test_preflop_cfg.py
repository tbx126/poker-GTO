"""Parameterised bet-tree configuration."""

import numpy as np
import pytest

from engine.hand_class import class_index
from solver.preflop import ACTIONS, PreflopSolver, TreeCfg


def test_default_cfg_matches_legacy():
    """Defaults must match the values originally hard-coded in M2.5."""
    cfg = TreeCfg()
    assert (cfg.stack, cfg.sb_blind, cfg.bb_blind) == (100.0, 0.5, 1.0)
    assert (cfg.open_to, cfg.threebet_to) == (2.5, 9.0)
    # fourbet_to defaults to stack via __post_init__ normalisation
    assert cfg.fourbet_to == 100.0


def test_invalid_ladder_rejected():
    with pytest.raises(ValueError, match="invalid bet ladder"):
        TreeCfg(open_to=2.0, threebet_to=2.0)  # 3bet must be strictly > open
    with pytest.raises(ValueError, match="invalid bet ladder"):
        TreeCfg(stack=10.0, threebet_to=12.0)  # 3bet beyond stack
    with pytest.raises(ValueError, match="invalid bet ladder"):
        TreeCfg(sb_blind=2.0, bb_blind=1.0)    # SB > BB illegal


def test_short_stack_pushfold_converges():
    """20bb HU push-fold-ish: small open / 3bet / shove room."""
    cfg = TreeCfg(stack=20.0, open_to=2.0, threebet_to=6.0)
    solver = PreflopSolver(cfg=cfg)
    solver.train(60)
    sigma_root = solver.average_strategy(())
    fold_idx = ACTIONS[()].index("fold")
    aa = class_index("AA")
    # AA must not fold even at 20bb
    assert sigma_root[fold_idx, aa] < 0.05
    # Junk should mostly fold
    assert sigma_root[fold_idx, class_index("72o")] > 0.6


def test_deep_stack_aa_does_not_fold():
    """At 200bb, AA must never fold (regardless of open-vs-shove split).

    Note: with the all-in equity abstraction we don't model postflop play,
    so AA may pick "shove" as much as "open" — this isn't realistic for
    real poker but is consistent with the model. We only assert the
    non-fold property here."""
    cfg = TreeCfg(stack=200.0, threebet_to=10.0, fourbet_to=200.0)
    solver = PreflopSolver(cfg=cfg)
    solver.train(50)
    sigma = solver.average_strategy(())
    fold_idx = ACTIONS[()].index("fold")
    aa = class_index("AA")
    assert sigma[fold_idx, aa] < 0.05


def test_open_size_affects_bb_defense():
    """Larger open size → BB defends tighter (fewer non-folds vs open)."""
    small = PreflopSolver(cfg=TreeCfg(open_to=2.0, threebet_to=6.5))
    big = PreflopSolver(cfg=TreeCfg(open_to=4.0, threebet_to=12.0))
    small.train(40)
    big.train(40)

    sigma_s = small.average_strategy(("open",))
    sigma_b = big.average_strategy(("open",))
    fold_idx = ACTIONS[("open",)].index("fold")

    # Marginal fold rate over hand classes (uniform-class-weighted approximation)
    fold_s = sigma_s[fold_idx].mean()
    fold_b = sigma_b[fold_idx].mean()
    assert fold_b > fold_s, f"bigger open should make BB fold more: {fold_b} vs {fold_s}"
