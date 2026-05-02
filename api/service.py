"""Pure functions that wrap the CFR+ solver — easy to test, no FastAPI deps."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from engine.hand_class import all_classes, class_index
from solver.cfr import CFRPlus, exploitability
from solver.games.kuhn import KuhnGame
from solver.games.leduc import LeducGame
from solver.preflop import ACTIONS as PREFLOP_ACTIONS, N as PREFLOP_N, PreflopSolver, TreeCfg

from api.schemas import (
    GameName,
    PreflopLock,
    PreflopPanel,
    PreflopRequest,
    PreflopResponse,
    SolveRequest,
    SolveResponse,
    StrategyEntry,
    TrajectoryPoint,
    TreeConfig,
)


def _make_game(name: GameName) -> Any:
    if name == "kuhn":
        return KuhnGame()
    if name == "leduc":
        return LeducGame()
    raise ValueError(f"unknown game: {name}")


def _action_labels(name: GameName, infoset: str) -> list[str]:
    """Recover per-infoset action labels for the response payload."""
    if name == "kuhn":
        return ["check/fold", "bet/call"]
    # Leduc actions per round-state (matches LeducGame.legal_actions order).
    # The infoset format is f"r{round}|rank|...|round_actions".
    parts = infoset.split("|")
    cur_actions = parts[-1]  # current round's action history when this infoset is reached
    if cur_actions == "" or cur_actions == "c":
        return ["check", "raise"]
    if cur_actions == "r" or cur_actions == "cr":
        return ["call", "raise", "fold"]
    if cur_actions == "rr" or cur_actions == "crr":
        return ["call", "fold"]
    return [f"a{i}" for i in range(10)]  # fallback (won't normally hit)


def solve(name: GameName, req: SolveRequest) -> SolveResponse:
    game = _make_game(name)
    solver = CFRPlus(game)
    started = time.perf_counter()

    chunk_size = max(1, req.iters // req.chunks)
    trajectory: list[TrajectoryPoint] = []
    done = 0
    while done < req.iters:
        step = min(chunk_size, req.iters - done)
        solver.train(step)
        done += step
        eps = exploitability(game, solver.average_strategies())
        trajectory.append(TrajectoryPoint(iter=done, exploitability=eps))

    avg = solver.average_strategies()
    strategies: list[StrategyEntry] = []
    for key in sorted(avg.keys()):
        probs = avg[key].tolist()
        labels = _action_labels(name, str(key))
        # Trim labels to match prob length (defensive — should already match).
        labels = labels[: len(probs)]
        strategies.append(StrategyEntry(infoset=str(key), actions=labels, probs=probs))

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return SolveResponse(
        game=name,
        iters=req.iters,
        final_exploitability=trajectory[-1].exploitability,
        trajectory=trajectory,
        strategies=strategies,
        elapsed_ms=elapsed_ms,
    )


# ----- preflop -----


def _bet_kind_from_pot_ratio(amount: float, pot: float) -> str:
    """Map a raise (chips, pot) to one of the frontend color buckets.

    Ratio = amount / pot_after_a_call. Tuned so 2.5x SB open lands at bet_75,
    pot-sized 3bet at bet_100, ~1.5× pot raise at bet_150, all-in at allin.
    """
    if pot <= 0:
        return "bet_100"
    r = amount / pot
    if r >= 3.0:
        return "allin"
    if r >= 1.6:
        return "bet_150"
    if r >= 1.05:
        return "bet_100"
    if r >= 0.65:
        return "bet_75"
    if r >= 0.40:
        return "bet_50"
    return "bet_25"


def _action_kinds_for_history(actions: list[str], cfg: TreeCfg) -> list[str]:
    """Compute frontend color bucket per action at this infoset, from cfg sizes."""
    fb = cfg.fourbet_to if cfg.fourbet_to is not None else cfg.stack
    out: list[str] = []
    for a in actions:
        if a == "fold":
            out.append("fold")
        elif a == "call":
            out.append("check_call")
        elif a == "shove":
            out.append("allin")
        elif a == "open":
            out.append(_bet_kind_from_pot_ratio(cfg.open_to - cfg.bb_blind, 2 * cfg.bb_blind))
        elif a == "3bet":
            out.append(_bet_kind_from_pot_ratio(cfg.threebet_to - cfg.open_to, 2 * cfg.open_to))
        elif a == "4bet":
            if fb >= cfg.stack - 1e-9:
                out.append("allin")
            else:
                out.append(_bet_kind_from_pot_ratio(fb - cfg.threebet_to, 2 * cfg.threebet_to))
        else:
            out.append("bet_100")
    return out


def _strategy_to_dict(sigma: np.ndarray) -> dict[str, list[float]]:
    """(n_actions, 169) -> {class_label: [prob_a0, prob_a1, ...]}."""
    classes = all_classes()
    out: dict[str, list[float]] = {}
    for i, cls in enumerate(classes):
        out[cls.label] = [float(p) for p in sigma[:, i]]
    return out


def _build_locks(req_locks: list[PreflopLock]) -> dict[tuple[str, ...], np.ndarray]:
    """Group request locks by history and build (n_actions, 169) NaN-masked arrays."""
    out: dict[tuple[str, ...], np.ndarray] = {}
    for lock in req_locks:
        history = tuple(lock.history)
        if history not in PREFLOP_ACTIONS:
            raise ValueError(f"unknown history: {history}; legal: {list(PREFLOP_ACTIONS.keys())}")
        actions_at_h = PREFLOP_ACTIONS[history]
        if len(lock.probs) != len(actions_at_h):
            raise ValueError(
                f"history {history} expects {len(actions_at_h)} probs, got {len(lock.probs)}"
            )
        prob_sum = sum(lock.probs)
        if abs(prob_sum - 1.0) > 1e-6:
            raise ValueError(f"probs for {lock.hand} at {history} sum to {prob_sum}, expected 1")
        if any(p < -1e-9 for p in lock.probs):
            raise ValueError(f"probs for {lock.hand} contain negatives")

        if history not in out:
            out[history] = np.full((len(actions_at_h), PREFLOP_N), np.nan)
        try:
            col = class_index(lock.hand)
        except KeyError as e:
            raise ValueError(f"unknown hand class: {lock.hand}") from e
        out[history][:, col] = lock.probs
    return out


def _make_cfg(req_cfg: TreeConfig) -> TreeCfg:
    return TreeCfg(
        stack=req_cfg.stack,
        sb_blind=req_cfg.sb_blind,
        bb_blind=req_cfg.bb_blind,
        open_to=req_cfg.open_to,
        threebet_to=req_cfg.threebet_to,
        fourbet_to=req_cfg.fourbet_to,
    )


def solve_preflop(req: PreflopRequest) -> PreflopResponse:
    started = time.perf_counter()
    cfg = _make_cfg(req.tree)
    locks = _build_locks(req.locks) if req.locks else None
    solver = PreflopSolver(locks=locks, cfg=cfg)
    solver.train(req.iters)

    sb_open_actions = PREFLOP_ACTIONS[()]
    bb_def_actions = PREFLOP_ACTIONS[("open",)]
    fb = cfg.fourbet_to if cfg.fourbet_to is not None else cfg.stack
    fb_label = "all-in" if abs(fb - cfg.stack) < 1e-9 else f"{fb:g}bb"
    common_subtitle = (
        f"{cfg.stack:g}bb HU · open {cfg.open_to:g} · 3bet {cfg.threebet_to:g} · 4bet {fb_label}"
    )

    panels = [
        PreflopPanel(
            side="BB",
            title="OOP — BB",
            subtitle=f"defense vs open · {common_subtitle}",
            history=["open"],
            actions=bb_def_actions,
            action_kinds=_action_kinds_for_history(bb_def_actions, cfg),
            by_class=_strategy_to_dict(solver.average_strategy(("open",))),
        ),
        PreflopPanel(
            side="SB",
            title="IP — SB",
            subtitle=f"opening range · {common_subtitle}",
            history=[],
            actions=sb_open_actions,
            action_kinds=_action_kinds_for_history(sb_open_actions, cfg),
            by_class=_strategy_to_dict(solver.average_strategy(())),
        ),
    ]

    return PreflopResponse(
        iters=solver.iter,
        final_exploitability=solver.exploitability(),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        panels=panels,
    )


# ----- Deep CFR postflop -----


def _parse_card(card_str: str):
    """Parse card string like 'Ah' to Card object."""
    from engine.cards import card_from_str
    return card_from_str(card_str)


def _action_to_postflop(action, game_state) -> dict:
    """Convert Action to PostflopAction dict."""
    from engine.actions import ActionKind
    
    kind_map = {
        ActionKind.FOLD: "FOLD",
        ActionKind.CHECK: "CHECK",
        ActionKind.CALL: "CALL",
        ActionKind.BET: "BET",
        ActionKind.RAISE: "RAISE",
    }
    
    kind = kind_map.get(action.kind, "UNKNOWN")
    amount = action.amount
    
    # Generate label
    if action.kind == ActionKind.FOLD:
        label = "Fold"
    elif action.kind == ActionKind.CHECK:
        label = "Check"
    elif action.kind == ActionKind.CALL:
        label = f"Call {amount}" if amount else "Call"
    elif action.kind == ActionKind.BET:
        label = f"Bet {amount}" if amount else "Bet"
    elif action.kind == ActionKind.RAISE:
        label = f"Raise {amount}" if amount else "Raise"
    else:
        label = kind
    
    return {
        "kind": kind,
        "amount": amount,
        "label": label,
    }


def solve_postflop(req: 'DeepCFRRequest') -> 'DeepCFRResponse':
    """Solve postflop using Deep CFR."""
    from api.schemas import (
        DeepCFRResponse,
        PostflopAction,
        PostflopStrategy,
    )
    from solver.deep_cfr.solver import DeepCFRSolver, DeepCFRConfig
    from solver.games.holdem import PostflopGame, BettingConfig, PostflopGameWithBoard
    
    started = time.perf_counter()
    
    # Create game config
    game_config = BettingConfig(
        stack=req.game_config.stack,
        pot=req.game_config.pot,
        bet_sizings=tuple(req.game_config.bet_sizings),
    )
    
    # Create game (with fixed board if specified)
    if req.board:
        board = tuple(_parse_card(c) for c in req.board)
        game = PostflopGameWithBoard(board, game_config)
    else:
        game = PostflopGame(game_config)
    
    # Create solver config
    solver_config = DeepCFRConfig(
        backbone_type=req.solver_config.backbone_type,
        num_iters=req.solver_config.num_iters,
        num_traversals=req.solver_config.num_traversals,
        learning_rate=req.solver_config.learning_rate,
    )
    
    # Train solver
    solver = DeepCFRSolver(game, solver_config)
    solver.train()
    
    # Collect strategies from visited states
    strategies = []
    board_str = [str(c) for c in (req.board or [])]
    
    # Sample some states to get strategies
    for _ in range(10):
        state = game.initial_state()
        if req.board:
            board_str = [str(c) for c in state.full_board[:5]]
        
        # Get strategy for initial state
        strategy = solver.get_strategy(state)
        actions = game.legal_actions(state)
        
        action_list = [_action_to_postflop(a, state) for a in actions]
        probs = [strategy.get(i, 0.0) for i in range(len(actions))]
        
        strategies.append(PostflopStrategy(
            infoset=game.infoset_key(state, 0),
            actions=[PostflopAction(**a) for a in action_list],
            probs=probs,
        ))
    
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    
    return DeepCFRResponse(
        iters=solver.iter,
        elapsed_ms=elapsed_ms,
        exploitability=solver.exploitability() if hasattr(solver, 'exploitability') else None,
        board=board_str,
        strategies=strategies[:10],  # Limit to 10 strategies
        training_losses={
            "player_0": solver.advantage_losses.get(0, []),
            "player_1": solver.advantage_losses.get(1, []),
            "strategy": solver.strategy_losses,
        },
    )
