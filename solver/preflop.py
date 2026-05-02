"""Heads-up No-Limit Hold'em preflop subgame with 169-class abstraction.

Tree (SB acts first), parameterised by `TreeCfg`:
  ()                            SB: fold | open | shove
    (fold,)                                              terminal: SB -sb_blind
    (open,)                     BB: fold | call | 3bet
      (open, fold)                                       terminal: SB +bb_blind
      (open, call)                                       SHOWDOWN, both = open_to
      (open, 3bet)              SB: fold | call | 4bet
        (open, 3bet, fold)                               terminal: SB -open_to
        (open, 3bet, call)                               SHOWDOWN, both = threebet_to
        (open, 3bet, 4bet)      BB: fold | call
          (open, 3bet, 4bet, fold)                       terminal: SB +threebet_to
          (open, 3bet, 4bet, call)                       SHOWDOWN, both = fourbet_to
    (shove,)                    BB: fold | call
      (shove, fold)                                      terminal: SB +bb_blind
      (shove, call)                                      SHOWDOWN, both = stack

Default cfg = 100bb HU cash (SB 0.5, BB 1, open 2.5x, 3bet to 9, 4bet allin).

Vectorised CFR+: walks the betting tree once per iteration, with 169×169
matrices flowing through (one entry per (SB-class, BB-class) chance branch).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from engine.equity import equity_table
from engine.hand_class import all_classes

SB = 0
BB = 1
N = 169


# --- bet tree configuration --------------------------------------------------


@dataclass(frozen=True)
class TreeCfg:
    """Heads-up bet ladder. Sizes are *total* commitment to that point,
    in big blinds (so `open_to=2.5` means SB raises to 2.5bb)."""

    stack: float = 100.0
    sb_blind: float = 0.5
    bb_blind: float = 1.0
    open_to: float = 2.5
    threebet_to: float = 9.0
    fourbet_to: Optional[float] = None  # None => stack (all-in)

    def __post_init__(self) -> None:
        fb = self.fourbet_to if self.fourbet_to is not None else self.stack
        if fb is None or fb <= 0:
            raise ValueError("fourbet_to must be positive")
        if not (
            0 < self.sb_blind < self.bb_blind <= self.open_to < self.threebet_to < fb <= self.stack
        ):
            raise ValueError(
                "invalid bet ladder: require "
                f"0 < sb({self.sb_blind}) < bb({self.bb_blind}) "
                f"<= open({self.open_to}) < 3bet({self.threebet_to}) "
                f"< 4bet({fb}) <= stack({self.stack})"
            )
        if self.fourbet_to is None:
            object.__setattr__(self, "fourbet_to", fb)


DEFAULT_CFG = TreeCfg()


# --- tree spec ---------------------------------------------------------------

ACTIONS: dict[tuple[str, ...], list[str]] = {
    (): ["fold", "open", "shove"],
    ("open",): ["fold", "call", "3bet"],
    ("shove",): ["fold", "call"],
    ("open", "3bet"): ["fold", "call", "4bet"],
    ("open", "3bet", "4bet"): ["fold", "call"],
}

CURRENT_PLAYER: dict[tuple[str, ...], int] = {
    (): SB,
    ("open",): BB,
    ("shove",): BB,
    ("open", "3bet"): SB,
    ("open", "3bet", "4bet"): BB,
}

_FOLD_TERMINALS = {
    ("fold",),
    ("open", "fold"),
    ("shove", "fold"),
    ("open", "3bet", "fold"),
    ("open", "3bet", "4bet", "fold"),
}
_SHOWDOWN_TERMINALS = {
    ("open", "call"),
    ("shove", "call"),
    ("open", "3bet", "call"),
    ("open", "3bet", "4bet", "call"),
}


def _is_terminal(h: tuple[str, ...]) -> bool:
    return h in _FOLD_TERMINALS or h in _SHOWDOWN_TERMINALS


def _terminal_sb_value(h: tuple[str, ...], E: np.ndarray, cfg: TreeCfg) -> np.ndarray:
    """SB's value as a 169×169 matrix indexed by (sb_class, bb_class)."""
    fb = cfg.fourbet_to if cfg.fourbet_to is not None else cfg.stack
    if h == ("fold",):
        return np.full((N, N), -cfg.sb_blind)
    if h == ("open", "fold"):
        return np.full((N, N), cfg.bb_blind)
    if h == ("shove", "fold"):
        return np.full((N, N), cfg.bb_blind)
    if h == ("open", "3bet", "fold"):
        return np.full((N, N), -cfg.open_to)
    if h == ("open", "3bet", "4bet", "fold"):
        return np.full((N, N), cfg.threebet_to)
    if h == ("open", "call"):
        return 2.0 * cfg.open_to * E - cfg.open_to
    if h == ("shove", "call"):
        return 2.0 * cfg.stack * E - cfg.stack
    if h == ("open", "3bet", "call"):
        return 2.0 * cfg.threebet_to * E - cfg.threebet_to
    if h == ("open", "3bet", "4bet", "call"):
        return 2.0 * fb * E - fb
    raise ValueError(f"not a terminal: {h}")


# --- chance prior -------------------------------------------------------------


def class_probability_vector() -> np.ndarray:
    """Marginal P(class) for each of the 169 classes. Sums to 1."""
    cls = all_classes()
    return np.array([c.combos / 1326.0 for c in cls], dtype=np.float64)


# --- vectorized solver --------------------------------------------------------


class PreflopSolver:
    """Tabular CFR+ over the HU preflop 169-class subgame.

    Optionally accepts `locks`: a mapping from `history` to a `(n_actions, 169)`
    array. Columns containing NaN remain free; non-NaN columns are clamped to
    the given strategy and excluded from regret updates. This lets callers
    pin "BTN always opens AA" or "BB never folds AKs" and re-solve the rest of
    the range against the constraint."""

    def __init__(
        self,
        equity_matrix: Optional[np.ndarray] = None,
        locks: Optional[dict[tuple[str, ...], np.ndarray]] = None,
        cfg: Optional[TreeCfg] = None,
    ) -> None:
        self.cfg = cfg if cfg is not None else DEFAULT_CFG
        self.E = (equity_matrix if equity_matrix is not None else equity_table()).astype(np.float64)
        if self.E.shape != (N, N):
            raise ValueError(f"equity_matrix must be {N}x{N}, got {self.E.shape}")
        self.p = class_probability_vector()
        self.pi_c = np.outer(self.p, self.p)  # 169×169 joint chance prior
        self.regrets: dict[tuple[str, ...], np.ndarray] = {}
        self.strategy_sums: dict[tuple[str, ...], np.ndarray] = {}
        self.iter = 0
        self.locks: dict[tuple[str, ...], np.ndarray] = {}
        self._locked_cols: dict[tuple[str, ...], np.ndarray] = {}
        if locks:
            for h, arr in locks.items():
                self.set_lock(h, arr)

    def set_lock(self, history: tuple[str, ...], lock: np.ndarray) -> None:
        """Pin strategy at one history. Pass NaN in columns to leave them free.

        `lock` shape: (n_actions, 169). Columns whose first entry is NaN are
        treated as unlocked. Other columns must sum to 1."""
        if history not in ACTIONS:
            raise KeyError(f"unknown decision history: {history}")
        n_actions = len(ACTIONS[history])
        if lock.shape != (n_actions, N):
            raise ValueError(f"lock shape {lock.shape} != ({n_actions}, {N})")
        locked_cols = ~np.isnan(lock[0])
        if locked_cols.any():
            cs = lock[:, locked_cols].sum(axis=0)
            if not np.allclose(cs, 1.0, atol=1e-6):
                raise ValueError(f"locked columns must sum to 1; got {cs.min()}..{cs.max()}")
            if (lock[:, locked_cols] < -1e-9).any():
                raise ValueError("lock probs must be non-negative")
        self.locks[history] = lock
        self._locked_cols[history] = locked_cols

    # ----- regret matching -----

    def _strategy(self, history: tuple[str, ...]) -> np.ndarray:
        n_actions = len(ACTIONS[history])
        if history not in self.regrets:
            self.regrets[history] = np.zeros((n_actions, N))
            self.strategy_sums[history] = np.zeros((n_actions, N))
        positive = np.maximum(self.regrets[history], 0.0)
        col_sums = positive.sum(axis=0, keepdims=True)
        sigma = np.where(col_sums > 0.0, positive / np.where(col_sums > 0, col_sums, 1.0), 1.0 / n_actions)
        if history in self.locks:
            cols = self._locked_cols[history]
            if cols.any():
                sigma[:, cols] = self.locks[history][:, cols]
        return sigma

    def average_strategy(self, history: tuple[str, ...]) -> np.ndarray:
        if history not in self.strategy_sums:
            n = len(ACTIONS[history])
            return np.full((n, N), 1.0 / n)
        s = self.strategy_sums[history]
        col_sums = s.sum(axis=0, keepdims=True)
        return np.where(col_sums > 0.0, s / np.where(col_sums > 0, col_sums, 1.0), 1.0 / s.shape[0])

    # ----- training walk -----

    def _walk(
        self,
        history: tuple[str, ...],
        traverser: int,
        opp_reach: np.ndarray,        # (169, 169)  joint chance × opp strategy
        trav_reach: np.ndarray,       # (169,)      traverser's strategy product, by their class
    ) -> np.ndarray:
        if _is_terminal(history):
            v_sb = _terminal_sb_value(history, self.E, self.cfg)
            return v_sb if traverser == SB else -v_sb

        cur = CURRENT_PLAYER[history]
        actions = ACTIONS[history]
        sigma = self._strategy(history)  # (n_a, 169) — col = current player's class

        V_a = np.empty((len(actions), N, N))
        for i in range(len(actions)):
            if cur == traverser:
                new_opp_reach = opp_reach
                new_trav_reach = trav_reach * sigma[i, :]
            else:
                new_trav_reach = trav_reach
                if cur == SB:
                    new_opp_reach = opp_reach * sigma[i, :, None]
                else:
                    new_opp_reach = opp_reach * sigma[i, None, :]
            V_a[i] = self._walk(history + (actions[i],), traverser, new_opp_reach, new_trav_reach)

        # Node value V[s, b] using current strategy.
        if cur == SB:
            V = np.einsum("as,asb->sb", sigma, V_a)
        else:
            V = np.einsum("ab,asb->sb", sigma, V_a)

        if cur == traverser:
            # Counterfactual values per (action, traverser_class).
            if cur == SB:
                cfv_a = np.einsum("sb,asb->as", opp_reach, V_a)   # (n_a, 169)
                cfv_node = np.einsum("sb,sb->s", opp_reach, V)    # (169,)
            else:
                cfv_a = np.einsum("sb,asb->ab", opp_reach, V_a)
                cfv_node = np.einsum("sb,sb->b", opp_reach, V)
            regret_delta = cfv_a - cfv_node[None, :]
            if history in self.locks:
                cols = self._locked_cols[history]
                if cols.any():
                    regret_delta[:, cols] = 0.0  # frozen — never deviate
            self.regrets[history] = np.maximum(self.regrets[history] + regret_delta, 0.0)
            # CFR+ linear weight = iter * traverser_reach.
            self.strategy_sums[history] += self.iter * (trav_reach[None, :] * sigma)

        return V

    def train(self, iters: int) -> None:
        for _ in range(iters):
            self.iter += 1
            for traverser in (SB, BB):
                self._walk((), traverser, self.pi_c.copy(), np.ones(N))

    # ----- evaluation -----

    def _walk_with_strategies(
        self,
        history: tuple[str, ...],
        sb_sigma_by_h: dict,
        bb_sigma_by_h: dict,
    ) -> np.ndarray:
        """Walk tree with fixed (avg) strategies; return SB-value 169×169 matrix."""
        if _is_terminal(history):
            return _terminal_sb_value(history, self.E, self.cfg)  # noqa: F811
        cur = CURRENT_PLAYER[history]
        actions = ACTIONS[history]
        sigma = sb_sigma_by_h[history] if cur == SB else bb_sigma_by_h[history]
        V_a = np.empty((len(actions), N, N))
        for i in range(len(actions)):
            V_a[i] = self._walk_with_strategies(history + (actions[i],), sb_sigma_by_h, bb_sigma_by_h)
        if cur == SB:
            return np.einsum("as,asb->sb", sigma, V_a)
        return np.einsum("ab,asb->sb", sigma, V_a)

    def _best_response_value(self, br_player: int, opp_avg: dict) -> float:
        """Walk tree letting br_player play optimally per (history, class). Return EV at root.

        The BR's argmax at each infoset must use the *path-conditional* opp class
        distribution, not the prior — this is the joint reach matrix flowing
        through opp's strategies."""
        E = self.E

        def walk(h: tuple[str, ...], opp_reach: np.ndarray) -> np.ndarray:
            if _is_terminal(h):
                v_sb = _terminal_sb_value(h, E, self.cfg)
                return v_sb if br_player == SB else -v_sb
            cur = CURRENT_PLAYER[h]
            actions = ACTIONS[h]
            V_a = np.empty((len(actions), N, N))
            for i in range(len(actions)):
                if cur == br_player:
                    new_opp_reach = opp_reach
                else:
                    sigma = opp_avg[h]
                    if cur == SB:
                        new_opp_reach = opp_reach * sigma[i, :, None]
                    else:
                        new_opp_reach = opp_reach * sigma[i, None, :]
                V_a[i] = walk(h + (actions[i],), new_opp_reach)

            if cur == br_player:
                # Q(a, my_class) = sum_{opp_class} opp_reach * V_a; pick argmax per my class.
                if cur == SB:
                    Q = np.einsum("sb,asb->as", opp_reach, V_a)  # (n_a, 169)
                else:
                    Q = np.einsum("sb,asb->ab", opp_reach, V_a)
                a_star = np.argmax(Q, axis=0)
                # BR sigma: one-hot at a_star for unlocked classes, locked freq for locked.
                br_sigma = np.zeros((len(actions), N))
                br_sigma[a_star, np.arange(N)] = 1.0
                if h in self.locks:
                    cols = self._locked_cols[h]
                    if cols.any():
                        br_sigma[:, cols] = self.locks[h][:, cols]
                if cur == SB:
                    return np.einsum("as,asb->sb", br_sigma, V_a)
                return np.einsum("ab,asb->sb", br_sigma, V_a)

            sigma = opp_avg[h]
            if cur == SB:
                return np.einsum("as,asb->sb", sigma, V_a)
            return np.einsum("ab,asb->sb", sigma, V_a)

        V = walk((), self.pi_c.copy())
        return float(np.sum(self.pi_c * V))

    def exploitability(self) -> float:
        """BR_SB(σ_BB) + BR_BB(σ_SB) — equals 0 at NE."""
        decision_histories = list(ACTIONS.keys())
        avg = {h: self.average_strategy(h) for h in decision_histories}
        # avg dict serves both SB-acting and BB-acting nodes (lookup by history)
        v_sb = self._best_response_value(SB, avg)
        v_bb = self._best_response_value(BB, avg)
        return v_sb + v_bb

