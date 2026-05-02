"""Tabular CFR+ for finite imperfect-information games.

Implements the canonical CFR+ pair:
  - regrets clamped to >= 0 immediately after each update
  - linear weighting: strategy_sum += iter * reach * strategy

For 2-player zero-sum games this gives an O(1/sqrt(T)) convergence to
Nash, in practice much faster (typically 1/T-ish empirically). The
solver works on any object implementing the `Game` protocol.

The neural value-net swap-in (Deep CFR) reuses this control flow but
replaces the regret/strategy tables with predictors. That comes in M3.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Hashable

import numpy as np

from solver.games.base import Game


class CFRPlus:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.regrets: dict[Hashable, np.ndarray] = {}
        self.strategy_sum: dict[Hashable, np.ndarray] = {}
        self.iter = 0

    def _strategy(self, key: Hashable, n_actions: int) -> np.ndarray:
        r = self.regrets.get(key)
        if r is None:
            self.regrets[key] = np.zeros(n_actions)
            self.strategy_sum[key] = np.zeros(n_actions)
            return np.full(n_actions, 1.0 / n_actions)
        positive = np.maximum(r, 0.0)
        s = positive.sum()
        if s > 0:
            return positive / s
        return np.full(n_actions, 1.0 / n_actions)

    def average_strategy(self, key: Hashable) -> np.ndarray:
        s = self.strategy_sum.get(key)
        if s is None:
            return np.array([])
        total = s.sum()
        if total > 0:
            return s / total
        return np.full(len(s), 1.0 / len(s))

    def average_strategies(self) -> dict[Hashable, np.ndarray]:
        return {k: self.average_strategy(k) for k in self.strategy_sum}

    def train(self, iters: int) -> None:
        for _ in range(iters):
            self.iter += 1
            for p in range(self.game.num_players):
                self._cfr(self.game.initial_state(), p, [1.0] * self.game.num_players)

    def _cfr(self, state, target_player: int, reach: list[float]) -> float:
        g = self.game
        if g.is_terminal(state):
            return g.utility(state, target_player)

        if g.is_chance(state):
            ev = 0.0
            for outcome, prob in g.chance_outcomes(state):
                # Chance probability belongs in counterfactual reach for the traverser:
                # multiply every non-traverser slot by `prob`. The traverser's own reach
                # tracks only their own action probabilities.
                new_reach = list(reach)
                for op in range(g.num_players):
                    if op != target_player:
                        new_reach[op] *= prob
                ev += prob * self._cfr(g.apply_chance(state, outcome), target_player, new_reach)
            return ev

        cur = g.current_player(state)
        actions = g.legal_actions(state)
        n = len(actions)
        key = g.infoset_key(state, cur)
        strategy = self._strategy(key, n)

        util = np.zeros(n)
        for i, a in enumerate(actions):
            new_reach = reach.copy()
            new_reach[cur] *= strategy[i]
            util[i] = self._cfr(g.apply(state, a), target_player, new_reach)
        node_util = float(np.dot(strategy, util))

        if cur == target_player:
            opp_reach = 1.0
            for op in range(g.num_players):
                if op != cur:
                    opp_reach *= reach[op]
            self.regrets[key] = np.maximum(self.regrets[key] + opp_reach * (util - node_util), 0.0)
            self.strategy_sum[key] += self.iter * reach[cur] * strategy

        return node_util


def best_response_value(
    game: Game,
    br_player: int,
    opp_strategy: dict[Hashable, np.ndarray],
    max_iters: int = 30,
) -> tuple[float, dict[Hashable, np.ndarray]]:
    """Return (BR value to br_player, BR pure strategy).

    Coordinate-ascent over BR's per-infoset action: walk the tree,
    accumulate Q[I][a] across all paths reaching infoset I, then for
    each I set BR[I] = argmax_a Q[I][a]. Iterate until stable. For
    finite IIGs this converges in ≤ |I| rounds.
    """
    br_strat: dict[Hashable, np.ndarray] = {}

    def get_strat(key: Hashable, n: int) -> np.ndarray:
        if key not in br_strat:
            br_strat[key] = np.full(n, 1.0 / n)
        return br_strat[key]

    Q: dict[Hashable, np.ndarray] = {}

    def walk(state, opp_reach: float) -> float:
        if game.is_terminal(state):
            return game.utility(state, br_player) * opp_reach
        if game.is_chance(state):
            tot = 0.0
            for o, prob in game.chance_outcomes(state):
                tot += walk(game.apply_chance(state, o), opp_reach * prob)
            return tot
        cur = game.current_player(state)
        actions = game.legal_actions(state)
        n = len(actions)
        if cur == br_player:
            key = game.infoset_key(state, br_player)
            strat = get_strat(key, n)
            child_vals = [walk(game.apply(state, a), opp_reach) for a in actions]
            if key not in Q:
                Q[key] = np.zeros(n)
            for i, cv in enumerate(child_vals):
                Q[key][i] += cv
            return float(np.dot(strat, child_vals))
        else:
            key = game.infoset_key(state, cur)
            strat = opp_strategy.get(key)
            if strat is None:
                strat = np.full(n, 1.0 / n)
            tot = 0.0
            for i, a in enumerate(actions):
                tot += walk(game.apply(state, a), opp_reach * strat[i])
            return tot

    last_v = 0.0
    for _ in range(max_iters):
        Q = {}
        last_v = walk(game.initial_state(), 1.0)
        changed = False
        for key, q in Q.items():
            n = len(q)
            best = int(np.argmax(q))
            new_strat = np.zeros(n)
            new_strat[best] = 1.0
            old = br_strat.get(key)
            if old is None or not np.array_equal(old, new_strat):
                br_strat[key] = new_strat
                changed = True
        if not changed:
            break

    # One more clean walk with the converged BR strategy
    Q = {}
    last_v = walk(game.initial_state(), 1.0)
    return last_v, br_strat


def exploitability(
    game: Game,
    avg_strategy: dict[Hashable, np.ndarray],
) -> float:
    """For 2-player zero-sum games: BR_P0(σ_1) + BR_P1(σ_0). Equals 0 at NE."""
    if game.num_players != 2:
        raise ValueError("exploitability defined here for 2-player games")
    v0, _ = best_response_value(game, 0, avg_strategy)
    v1, _ = best_response_value(game, 1, avg_strategy)
    return v0 + v1
