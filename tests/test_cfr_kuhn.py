"""CFR+ on Kuhn poker — must converge to known NE value (-1/18 for P1)."""

import numpy as np

from solver.cfr import CFRPlus, best_response_value, exploitability
from solver.games.kuhn import KuhnGame


def _analytical_ne(alpha: float = 1.0 / 3.0) -> dict:
    """Family of Kuhn NE strategies parameterized by α ∈ [0, 1/3]."""
    return {
        # P1 first action — order: [check 'p', bet 'b']
        "0|": np.array([1.0 - alpha, alpha]),       # J: bluff with prob α
        "1|": np.array([1.0, 0.0]),                  # Q: never bet
        "2|": np.array([1.0 - 3 * alpha, 3 * alpha]),# K: bet with prob 3α
        # P1 facing P-B — order: [fold 'p', call 'b']
        "0|pb": np.array([1.0, 0.0]),                # J: always fold
        "1|pb": np.array([2.0 / 3 - alpha, 1.0 / 3 + alpha]),  # Q: call (1/3 + α)
        "2|pb": np.array([0.0, 1.0]),                # K: always call
        # P2 after P1 check — order: [check 'p', bet 'b']
        "0|p": np.array([2.0 / 3, 1.0 / 3]),         # J: bluff bet 1/3
        "1|p": np.array([1.0, 0.0]),                 # Q: always check
        "2|p": np.array([0.0, 1.0]),                 # K: always bet
        # P2 facing P1 bet — order: [fold 'p', call 'b']
        "0|b": np.array([1.0, 0.0]),                 # J: always fold
        "1|b": np.array([2.0 / 3, 1.0 / 3]),         # Q: call 1/3
        "2|b": np.array([0.0, 1.0]),                 # K: always call
    }


def test_br_recovers_ne_value_at_alpha_one_third():
    """BR vs analytical NE must equal NE value (-1/18 for P1, +1/18 for P2)."""
    game = KuhnGame()
    ne = _analytical_ne(alpha=1.0 / 3.0)
    v0, _ = best_response_value(game, 0, ne)
    v1, _ = best_response_value(game, 1, ne)
    assert abs(v0 - (-1.0 / 18.0)) < 1e-9, f"P1 BR vs NE = {v0}, expected -1/18"
    assert abs(v1 - (1.0 / 18.0)) < 1e-9, f"P2 BR vs NE = {v1}, expected +1/18"
    # Exploitability of NE must be exactly 0
    assert abs(v0 + v1) < 1e-9


def test_br_recovers_ne_value_at_alpha_zero():
    """Same check at the other extreme of the NE family."""
    game = KuhnGame()
    ne = _analytical_ne(alpha=0.0)
    v0, _ = best_response_value(game, 0, ne)
    v1, _ = best_response_value(game, 1, ne)
    assert abs(v0 - (-1.0 / 18.0)) < 1e-9
    assert abs(v1 - (1.0 / 18.0)) < 1e-9


def test_kuhn_cfrplus_converges():
    """CFR+ exploitability must decrease monotonically and reach a tight bound."""
    game = KuhnGame()
    solver = CFRPlus(game)

    eps_at = []
    for _ in range(10):
        solver.train(2000)
        eps_at.append(exploitability(game, solver.average_strategies()))

    # Strict: each chunk improves on the previous (allowing 1e-6 numerical slack)
    for prev, cur in zip(eps_at, eps_at[1:]):
        assert cur <= prev + 1e-6, f"exploitability regressed: {prev} -> {cur}"
    # End state: exploitability < 5e-3 after 20k iters (game value scale ~1)
    assert eps_at[-1] < 5e-3, f"final exploitability {eps_at[-1]} not tight enough"


def test_kuhn_value_matches_known_ne():
    """Known: NE value to P1 in Kuhn = -1/18 ≈ -0.0556."""
    game = KuhnGame()
    solver = CFRPlus(game)
    solver.train(10000)
    avg = solver.average_strategies()

    # P1 best response value against P2's avg strategy = upper bound on P1's NE value
    v0, _ = best_response_value(game, 0, avg)
    # P2 best response value against P1's avg
    v1, _ = best_response_value(game, 1, avg)

    # Both should be very close to ±1/18 at NE
    assert abs(v0 - (-1.0 / 18.0)) < 5e-3, f"P1 BR value {v0} vs expected -1/18"
    assert abs(v1 - (1.0 / 18.0)) < 5e-3, f"P2 BR value {v1} vs expected 1/18"


def test_kuhn_average_strategy_known_form():
    """K always bets, J never calls, J bluffs from P2 in checked-to spot at ~1/3."""
    game = KuhnGame()
    solver = CFRPlus(game)
    solver.train(10000)

    # P1 with K, empty history -> bet ('b') with high prob
    avg_K_first = solver.average_strategy("2|")
    # action order is ['p', 'b']
    assert avg_K_first[1] > 0.5, f"K bets at {avg_K_first[1]}, expected high"

    # P1 with J, empty history -> rarely bets (alpha ≤ 1/3)
    avg_J_first = solver.average_strategy("0|")
    assert avg_J_first[1] <= 0.4, f"J bets at {avg_J_first[1]}, expected ≤ 1/3"

    # P2 with J, history='p' (P1 checked) -> bet (bluff) ~1/3
    avg_J_p2_p = solver.average_strategy("0|p")
    assert 0.15 < avg_J_p2_p[1] < 0.55, f"J bluff freq {avg_J_p2_p[1]} out of band"

    # P2 with K facing bet -> always call
    avg_K_p2_b = solver.average_strategy("2|b")
    assert avg_K_p2_b[1] > 0.95, f"K call freq {avg_K_p2_b[1]} too low"
