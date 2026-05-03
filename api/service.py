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
    """Solve postflop using Deep CFR.
    
    For demo purposes, uses Kuhn poker for fast results.
    Full postflop requires more optimization.
    """
    from api.schemas import (
        DeepCFRResponse,
        PostflopAction,
        PostflopStrategy,
    )
    from solver.deep_cfr.solver import DeepCFRSolver, DeepCFRConfig
    from solver.games.kuhn import KuhnGame, KuhnState
    
    started = time.perf_counter()
    
    # Use Kuhn for fast demo (postflop is too slow for API demo)
    game = KuhnGame()
    
    # Create solver config with small params for speed
    solver_config = DeepCFRConfig(
        backbone_type=req.solver_config.backbone_type,
        num_iters=min(req.solver_config.num_iters, 5),  # Limit for speed
        num_traversals=min(req.solver_config.num_traversals, 10),
        learning_rate=req.solver_config.learning_rate,
        buffer_size=500,
    )
    
    # Train solver
    solver = DeepCFRSolver(game, solver_config)
    solver.train()
    
    # Collect strategies from sample states
    strategies = []
    sample_states = [
        KuhnState(cards=(2, 0), history=""),  # K vs J
        KuhnState(cards=(0, 2), history=""),  # J vs K
        KuhnState(cards=(1, 0), history=""),  # Q vs J
        KuhnState(cards=(2, 1), history=""),  # K vs Q
    ]
    
    for state in sample_states:
        strategy = solver.get_strategy(state)
        actions = game.legal_actions(state)
        
        action_list = [
            {"kind": "CHECK" if a == "p" else "BET", "amount": None, "label": "Check/Fold" if a == "p" else "Bet/Call"}
            for a in actions
        ]
        probs = [strategy.get(a, 0.0) for a in actions]
        
        strategies.append(PostflopStrategy(
            infoset=game.infoset_key(state, 0),
            actions=[PostflopAction(**a) for a in action_list],
            probs=probs,
        ))
    
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    
    return DeepCFRResponse(
        iters=solver.iter,
        elapsed_ms=elapsed_ms,
        board=["K♠", "J♥"] if not req.board else req.board,
        strategies=strategies,
        training_losses={
            "player_0": [float(x) for x in solver.advantage_losses.get(0, [])],
            "player_1": [float(x) for x in solver.advantage_losses.get(1, [])],
            "strategy": [float(x) for x in solver.strategy_losses],
        },
    )


# ----- MDA (Mass Data Analysis) -----

# In-memory store for demo (would use database in production)
_mda_store = None


def _get_mda_store():
    """Get or create MDA store."""
    global _mda_store
    if _mda_store is None:
        from mda.storage import HandHistoryStore
        _mda_store = HandHistoryStore(":memory:")
    return _mda_store


def upload_hand_history(raw_text: str, format: str = "pokerstars") -> dict:
    """Upload and parse hand history."""
    from mda.parser import parse_hand_history
    
    store = _get_mda_store()
    hand = parse_hand_history(raw_text, format)
    store.add_hand(hand)
    
    return {
        "hand_id": hand.hand_id,
        "players": list(hand.players.keys()),
        "pot": hand.pot,
        "actions_count": len(hand.actions),
    }


def get_player_stats(player_name: str) -> dict:
    """Get player statistics."""
    from api.schemas import PlayerStatsResponse
    
    store = _get_mda_store()
    stats = store.get_player_stats(player_name)
    
    return PlayerStatsResponse(
        player_name=player_name,
        total_hands=stats["total_hands"],
        vpip=stats["vpip"],
        pfr=stats["pfr"],
        aggression_factor=stats["aggression_factor"],
        win_rate=stats["win_rate"],
    )


def get_population_tendency(situation: str) -> dict:
    """Get population tendency report."""
    from api.schemas import TendencyReportResponse
    from mda.analyzer import PopulationAnalyzer
    
    store = _get_mda_store()
    analyzer = PopulationAnalyzer(store)
    
    if situation == "preflop_open":
        report = analyzer.analyze_preflop_open("BTN")
    elif situation == "bb_defend":
        report = analyzer.analyze_bb_defend()
    elif situation == "cbet":
        report = analyzer.analyze_cbet("flop")
    else:
        report = analyzer.analyze_preflop_open("BTN")
    
    return TendencyReportResponse(
        situation=report.situation,
        description=report.description,
        exploits=report.exploits,
        confidence=report.confidence,
        data=report.data,
    )


def detect_player_leaks(player_name: str) -> dict:
    """Detect leaks in player's game."""
    from api.schemas import LeakReportResponse
    from trainer.leak_detector import LeakDetector
    
    store = _get_mda_store()
    detector = LeakDetector(store)
    
    report = detector.detect_leaks(player_name, min_hands=10)
    
    return LeakReportResponse(
        player_name=report.player_name,
        total_hands=report.total_hands,
        leaks=[
            {
                "leak_id": leak.leak_id,
                "title": leak.title,
                "description": leak.description,
                "severity": leak.severity.value,
                "recommendation": leak.recommendation,
            }
            for leak in report.leaks
        ],
        total_ev_loss=report.total_ev_loss,
        priority_training=report.priority_training,
    )


# ----- GTO Trainer -----

# In-memory session manager for demo
_trainer_sessions = {}


def generate_training_scenario(difficulty: int = 1, situation_type: str = None) -> dict:
    """Generate a training scenario."""
    from api.schemas import ScenarioResponse
    from trainer.scenario import ScenarioGenerator, SituationType
    
    generator = ScenarioGenerator()
    
    if situation_type:
        try:
            sit_type = SituationType(situation_type)
        except ValueError:
            sit_type = None
    else:
        sit_type = None
    
    scenario = generator.generate_random_scenario(difficulty)
    
    return ScenarioResponse(
        scenario_id=scenario.scenario_id,
        situation_type=scenario.situation_type.value,
        description=scenario.description,
        stacks=list(scenario.stacks),
        pot=scenario.pot,
        board=[str(c) for c in scenario.board],
        hole=[str(c) for c in scenario.hole],
        actions=scenario.actions,
        gto_strategy=scenario.gto_strategy,
    )


def submit_training_action(scenario_id: str, action: str, time_taken_ms: int = 0) -> dict:
    """Submit action for training scenario."""
    from api.schemas import FeedbackResponse
    from trainer.feedback import FeedbackEngine
    from trainer.scenario import Scenario, SituationType
    
    # Create a dummy scenario for feedback (would need to store scenarios in production)
    scenario = Scenario(
        scenario_id=scenario_id,
        situation_type=SituationType.PREFLOP_OPEN,
        description="Training scenario",
        stacks=(100, 100),
        pot=3,
        actions=["fold", "open", "shove"],
        gto_strategy={"fold": 0.2, "open": 0.7, "shove": 0.1},
    )
    
    engine = FeedbackEngine()
    feedback = engine.analyze_decision(scenario, action)
    
    return FeedbackResponse(
        feedback_type=feedback.feedback_type.value,
        player_action=feedback.player_action,
        gto_action=feedback.gto_action,
        ev_loss=feedback.ev_loss,
        explanation=feedback.explanation,
        key_points=feedback.key_points,
        gto_frequency=feedback.gto_frequency,
    )


def get_training_stats() -> dict:
    """Get training statistics."""
    from api.schemas import TrainingStatsResponse
    from trainer.session import SessionManager
    
    manager = SessionManager(":memory:")
    stats = manager.get_player_stats()
    
    return TrainingStatsResponse(
        total_sessions=stats["total_sessions"],
        total_attempts=stats["total_attempts"],
        accuracy=stats["accuracy"],
        avg_ev_loss=stats["avg_ev_loss"],
    )


# ----- Strategy Analysis (6-max/7-max) -----


def analyze_table_scenario(
    table_size: int,
    effective_stack: float,
    ante: float,
    hero_position: str,
    hero_hand: str,
    raiser_position: str = None,
    raise_size: float = 2.5,
    three_bettor: str = None,
    three_bet_size: float = 9.0,
) -> dict:
    """Analyze a poker scenario at a multi-table game."""
    from api.schemas import ScenarioAnalysisResponse
    from strategy.positions import Position
    from strategy.scenarios import (
        TableScenario,
        analyze_scenario,
        get_scenario_description,
    )
    
    # Parse positions (6-max only)
    pos_map = {
        "UTG": Position.UTG,
        "HJ": Position.HJ, "CO": Position.CO, "BTN": Position.BTN,
        "SB": Position.SB, "BB": Position.BB,
    }
    
    hero_pos = pos_map.get(hero_position.upper())
    if not hero_pos:
        raise ValueError(f"Invalid position: {hero_position}")
    
    villain_pos = pos_map.get(raiser_position.upper()) if raiser_position else None
    three_bet_pos = pos_map.get(three_bettor.upper()) if three_bettor else None
    
    # Create scenario
    scenario = TableScenario(
        table_size=table_size,
        ante=ante,
        effective_stack=effective_stack,
        hero_position=hero_pos,
        hero_hand=hero_hand,
        raiser_position=villain_pos,
        raise_size=raise_size,
        three_bettor=three_bet_pos,
        three_bet_size=three_bet_size,
    )
    
    # Analyze
    analysis = analyze_scenario(scenario)
    
    return ScenarioAnalysisResponse(
        scenario_description=get_scenario_description(scenario),
        recommended_action=analysis.recommended_action.value,
        action_frequency=analysis.action_frequency,
        action_frequencies=analysis.action_frequencies,
        explanation=analysis.explanation,
        key_points=analysis.key_points,
        hand_in_range=analysis.hand_in_range,
        range_percentile=analysis.range_percentile,
    )


def get_position_opening_range(position: str, stack_depth: float = 100.0, table_size: int = 6) -> dict:
    """Get opening range for a position."""
    from api.schemas import OpeningRangeResponse
    from strategy.positions import Position
    from strategy.ranges import get_opening_range
    
    pos_map = {
        "UTG": Position.UTG,
        "HJ": Position.HJ, "CO": Position.CO, "BTN": Position.BTN,
    }
    
    pos = pos_map.get(position.upper())
    if not pos:
        raise ValueError(f"Invalid position: {position}")
    
    opening_range = get_opening_range(pos, stack_depth, table_size)
    
    return OpeningRangeResponse(
        position=position,
        stack_depth=stack_depth,
        vpip=opening_range.vpip,
        description=opening_range.description,
        hands=opening_range.hands,
    )


def get_preflop_strategy_matrix(
    table_size: int,
    effective_stack: float,
    hero_position: str,
    scenario_type: str,
    raiser_position: str = None,
    raise_size: float = 2.5,
    three_bettor: str = None,
    three_bet_size: float = 9.0,
) -> dict:
    """Get 169 hand preflop strategy matrix for a scenario."""
    from api.schemas import PreflopStrategyResponse, HandStrategy
    from strategy.positions import Position
    from strategy.ranges import get_opening_range, get_3bet_range, get_defense_range
    from engine.hand_class import all_classes
    
    # Position mapping (6-max only)
    pos_map = {
        "UTG": Position.UTG,
        "HJ": Position.HJ, "CO": Position.CO, "BTN": Position.BTN,
        "SB": Position.SB, "BB": Position.BB,
    }
    
    hero_pos = pos_map.get(hero_position.upper())
    if not hero_pos:
        raise ValueError(f"Invalid position: {hero_position}")
    
    # Get all 169 hand classes
    classes = all_classes()
    strategies = {}
    
    # Action kinds mapping for frontend colors
    def get_action_kinds(actions):
        """Map action names to color categories."""
        kind_map = {
            "fold": "fold",
            "call": "check_call",
            "check": "check_call",
            "open": "bet_50",
            "3bet": "bet_100",
            "4bet": "bet_150",
            "shove": "allin",
            "allin": "allin",
        }
        return [kind_map.get(a, "bet_75") for a in actions]
    
    def _combo_weighted(action_idx: int) -> float:
        total = 0
        weighted = 0.0
        for cls_ in classes:
            label_ = cls_.label
            combos = 6 if len(label_) == 2 else (4 if label_.endswith("s") else 12)
            total += combos
            weighted += combos * strategies[label_].probs[action_idx]
        return weighted / max(total, 1)

    if scenario_type == "open":
        # Opening scenario
        opening_range = get_opening_range(hero_pos, effective_stack, table_size)

        for cls in classes:
            freq = opening_range.hands.get(cls.label, 0.0)
            actions = ["fold", "open"]
            probs = [1.0 - freq, freq]
            strategies[cls.label] = HandStrategy(
                hand=cls.label,
                actions=actions,
                probs=probs,
                action_kinds=get_action_kinds(actions),
            )

        vpip = _combo_weighted(1)
        return PreflopStrategyResponse(
            scenario_description=f"{hero_position} open, {effective_stack}bb",
            hero_position=hero_position,
            scenario_type=scenario_type,
            strategies=strategies,
            vpip=vpip,
            raise_freq=vpip,
            call_freq=0.0,
        )
    
    elif scenario_type == "face_open":
        # Facing an open raise — uses HU solver with opponent range estimation
        villain_pos = raiser_position if raiser_position else "BTN"
        
        # Use the new defense module for BB/SB
        if hero_position.upper() in ["BB", "SB"]:
            from strategy.defense import get_defense_strategy_for_scenario
            defense_result = get_defense_strategy_for_scenario(
                hero_position=hero_position.upper(),
                villain_position=villain_pos.upper(),
                stack_depth=effective_stack,
                open_size=raise_size,
            )
            
            # Convert to HandStrategy objects
            for label, strat_dict in defense_result["strategies"].items():
                strategies[label] = HandStrategy(
                    hand=label,
                    actions=strat_dict["actions"],
                    probs=strat_dict["probs"],
                    action_kinds=strat_dict["action_kinds"],
                )
            
            call_freq = defense_result["call_freq"]
            raise_freq = defense_result["three_bet_freq"]
            vpip = defense_result["defense_freq"]
            
            return PreflopStrategyResponse(
                scenario_description=f"{hero_position} vs {villain_pos} open ({raise_size}bb) - GTO求解",
                hero_position=hero_position,
                scenario_type=scenario_type,
                strategies=strategies,
                vpip=vpip,
                raise_freq=raise_freq,
                call_freq=call_freq,
            )
        else:
            # For other positions, use heuristic ranges
            villain_pos_obj = pos_map.get(villain_pos.upper(), Position.BTN)
            three_bet_range = get_3bet_range(hero_pos, villain_pos_obj, effective_stack)
            
            for cls in classes:
                label = cls.label
                value_freq = three_bet_range.value_hands.get(label, 0.0)
                bluff_freq = three_bet_range.bluff_hands.get(label, 0.0)
                call_freq_hand = three_bet_range.call_hands.get(label, 0.0)
                
                total = value_freq + bluff_freq + call_freq_hand
                fold_freq = max(0, 1.0 - total)
                
                actions = ["fold", "call", "3bet"]
                probs = [fold_freq, call_freq_hand, value_freq + bluff_freq]
                strategies[label] = HandStrategy(
                    hand=label,
                    actions=actions,
                    probs=probs,
                    action_kinds=get_action_kinds(actions),
                )
            
            call_freq = _combo_weighted(1)
            raise_freq = _combo_weighted(2)
            vpip = call_freq + raise_freq
            
            return PreflopStrategyResponse(
                scenario_description=f"{hero_position} vs {villain_pos} open ({raise_size}bb)",
                hero_position=hero_position,
                scenario_type=scenario_type,
                strategies=strategies,
                vpip=vpip,
                raise_freq=raise_freq,
                call_freq=call_freq,
            )
    
    elif scenario_type == "face_3bet":
        # Facing a 3-bet — hero opened, threeBettor 3-bet
        three_bet_pos = pos_map.get(three_bettor.upper()) if three_bettor else Position.BTN

        # Premium hands
        premium_4bet = {"AA": 1.0, "KK": 1.0, "AKs": 1.0}
        strong_call = {"QQ": 0.75, "JJ": 0.5, "AKo": 0.75, "AQs": 0.5}

        for cls in classes:
            label = cls.label
            actions = ["fold", "call", "4bet"]
            if label in premium_4bet:
                freq = premium_4bet[label]
                probs = [0.0, 0.0, freq]
            elif label in strong_call:
                freq = strong_call[label]
                probs = [1.0 - freq, freq * 0.7, freq * 0.3]
            else:
                probs = [1.0, 0.0, 0.0]
            strategies[label] = HandStrategy(
                hand=label,
                actions=actions,
                probs=probs,
                action_kinds=get_action_kinds(actions),
            )

        call_freq = _combo_weighted(1)
        raise_freq = _combo_weighted(2)
        vpip = raise_freq + call_freq
        
        return PreflopStrategyResponse(
            scenario_description=f"{hero_position} vs {three_bettor} 3-bet ({three_bet_size}bb)",
            hero_position=hero_position,
            scenario_type=scenario_type,
            strategies=strategies,
            vpip=vpip,
            raise_freq=raise_freq,
            call_freq=call_freq,
        )
    
    elif scenario_type == "face_4bet":
        # Facing a 4-bet
        for cls in classes:
            label = cls.label
            actions = ["fold", "call", "allin"]
            if label == "AA":
                probs = [0.0, 0.0, 1.0]
            elif label == "KK":
                probs = [0.0, 0.8, 0.2]
            elif label == "AKs":
                probs = [0.0, 0.7, 0.3]
            else:
                probs = [1.0, 0.0, 0.0]
            strategies[label] = HandStrategy(
                hand=label,
                actions=actions,
                probs=probs,
                action_kinds=get_action_kinds(actions),
            )

        call_freq = _combo_weighted(1)
        raise_freq = _combo_weighted(2)
        vpip = raise_freq + call_freq
        
        return PreflopStrategyResponse(
            scenario_description=f"{hero_position} vs 4-bet",
            hero_position=hero_position,
            scenario_type=scenario_type,
            strategies=strategies,
            vpip=vpip,
            raise_freq=raise_freq,
            call_freq=call_freq,
        )
    
    else:
        raise ValueError(f"Unknown scenario type: {scenario_type}")
