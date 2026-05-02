"""Leduc state-machine sanity + CFR+ convergence."""

from solver.cfr import CFRPlus, exploitability
from solver.games.leduc import LeducGame, LeducState, _round_commit


def test_round_commit_basic():
    assert _round_commit("rc", 2) == (2, 2)
    assert _round_commit("rrc", 2) == (4, 4)
    assert _round_commit("crrc", 4) == (8, 8)
    assert _round_commit("rf", 2) == (2, 0)
    assert _round_commit("rrf", 2) == (2, 4)


def test_terminal_after_round2_close():
    g = LeducGame()
    s = LeducState(p1_rank=0, p2_rank=1, public_rank=2, round1="cc", round2="cc")
    assert g.is_terminal(s)


def test_terminal_after_fold_in_round1():
    """Fold detected from action history alone — no separate fold flag needed."""
    g = LeducGame()
    s = LeducState(p1_rank=0, p2_rank=1, public_rank=None, round1="rf")
    assert g.is_terminal(s)
    # P2 was the folder ('rf' means P1 raised, P2 folded)
    # P1 contributed 1 ante + 2 raise = 3. P2 contributed 1 ante. Pot = 4.
    # P1 wins -> +1, P2 -> -1.
    assert g.utility(s, 0) == 1.0
    assert g.utility(s, 1) == -1.0


def test_utility_zero_sum_full_action():
    g = LeducGame()
    s = LeducState(p1_rank=2, p2_rank=0, public_rank=1, round1="rrc", round2="rrc")
    # commit r1: 4,4; r2: 8,8; antes 1,1 -> total 13 each, pot 26
    # P1 (K) vs P2 (J), public Q: no pair, K beats J -> P1 wins
    assert g.utility(s, 0) == 13.0
    assert g.utility(s, 1) == -13.0


def test_utility_pair_beats_high_card():
    g = LeducGame()
    s = LeducState(p1_rank=0, p2_rank=2, public_rank=0, round1="rc", round2="rc")
    # P1 has pair JJ (matches public), P2 has K high. P1 wins.
    assert g.utility(s, 0) == 7.0
    assert g.utility(s, 1) == -7.0


def test_utility_tie_split():
    g = LeducGame()
    s = LeducState(p1_rank=0, p2_rank=0, public_rank=1, round1="cc", round2="cc")
    # Both J, public Q. Neither pairs, both J-high -> tie.
    assert g.utility(s, 0) == 0.0
    assert g.utility(s, 1) == 0.0


def test_chance_outcomes_private_probabilities_sum_to_one():
    g = LeducGame()
    s = g.initial_state()
    outs = g.chance_outcomes(s)
    assert abs(sum(p for _, p in outs) - 1.0) < 1e-12
    assert len(outs) == 9  # 3 ranks × 3 ranks


def test_chance_outcomes_public_remaining_distribution():
    g = LeducGame()
    # Both players got J (rank 0). Remaining: 0 J, 2 Q, 2 K.
    s = LeducState(p1_rank=0, p2_rank=0, public_rank=None)
    outs = dict(g.chance_outcomes(s))
    assert 0 not in outs
    assert outs[1] == 0.5
    assert outs[2] == 0.5


def test_cfrplus_leduc_converges():
    """Exploitability must trend monotonically downward and end small."""
    game = LeducGame()
    solver = CFRPlus(game)

    eps = []
    for _ in range(5):
        solver.train(200)
        eps.append(exploitability(game, solver.average_strategies()))

    # Monotonic decrease (allow 1e-6 slack)
    for prev, cur in zip(eps, eps[1:]):
        assert cur <= prev + 1e-6, f"exploitability regressed: {eps}"
    # End point: must be at least 30% below the start, and < 1 chip
    assert eps[-1] < eps[0] * 0.7, f"insufficient improvement: {eps}"
    assert eps[-1] < 1.0, f"final exploitability {eps[-1]} too large"
