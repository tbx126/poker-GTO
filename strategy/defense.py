"""6-max preflop strategy using hybrid approach.

For BB/SB facing opens, uses heuristic defense ranges based on GTO principles.
For other scenarios, uses heuristic ranges from strategy.ranges.

Key insight: BB/SB defense is well-studied and we can use established GTO
approximations rather than running a full solver for each scenario.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from engine.hand_class import all_classes, class_index


# ============================================================
# Opponent Range Estimation
# ============================================================

# Opening range percentages by position (GTO-approximate)
OPEN_RANGE_PCT = {
    "UTG": 0.18,
    "HJ": 0.22,
    "CO": 0.30,
    "BTN": 0.42,
}


def estimate_opening_range(position: str, stack_depth: float = 100.0) -> np.ndarray:
    """Estimate opponent's opening range based on position and stack depth.
    
    Returns 169-length array with opening frequency for each hand class.
    """
    classes = all_classes()
    n = len(classes)
    freq = np.zeros(n)
    
    # Base range percentage
    base_pct = OPEN_RANGE_PCT.get(position.upper(), 0.25)
    
    # Stack depth adjustment
    if stack_depth <= 25:
        adj = 0.85
    elif stack_depth <= 60:
        adj = 0.95
    elif stack_depth <= 150:
        adj = 1.0
    else:
        adj = 1.08
    
    target_pct = base_pct * adj
    
    # Sort hands by strength
    hand_scores = []
    for i, cls in enumerate(classes):
        score = _hand_score(cls)
        hand_scores.append((i, score))
    
    hand_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Build range
    cumulative = 0.0
    for idx, score in hand_scores:
        cls = classes[idx]
        hand_pct = cls.combos / 1326.0
        
        if cumulative + hand_pct <= target_pct + 0.01:
            freq[idx] = 1.0
            cumulative += hand_pct
        else:
            remaining = target_pct - cumulative
            if remaining > 0 and hand_pct > 0:
                freq[idx] = remaining / hand_pct
            break
    
    return freq


def _hand_score(cls) -> float:
    """Simple hand strength heuristic for range construction."""
    high = cls.high
    low = cls.low
    
    score = high * 13 + low
    
    if cls.kind == "pair":
        score += 50 + high * 2
    elif cls.kind == "suited":
        score += 20
    
    return score


# ============================================================
# GTO Defense Ranges (Well-studied approximations)
# ============================================================

@dataclass
class DefenseStrategy:
    """Computed defense strategy for BB/SB facing an open."""
    hero_position: str
    villain_position: str
    stack_depth: float
    
    # Strategy for each hand class (169 arrays)
    fold_freq: np.ndarray
    call_freq: np.ndarray
    three_bet_freq: np.ndarray
    
    # Summary stats
    defense_freq: float
    three_bet_freq_total: float
    call_freq_total: float
    
    # Explanation
    explanation: str
    key_points: list[str]


def _get_bb_defense_range_vs_position(villain_position: str) -> dict:
    """Get GTO-approximate BB defense ranges vs different positions.
    
    Returns dict with hand -> (fold, call, 3bet) frequencies.
    These are based on established GTO solutions.
    """
    classes = all_classes()
    
    # Base defense ranges (simplified GTO approximation)
    # These are based on pot odds and equity calculations
    
    # Pot odds: BB needs ~33% equity to call a 2.5x open
    # With position disadvantage, BB should defend ~40-50% of hands
    
    ranges = {}
    
    for cls in classes:
        label = cls.label
        score = _hand_score(cls)
        
        # Determine hand strength category
        if cls.kind == "pair":
            rank = cls.high
            if rank >= 10:  # TT+
                ranges[label] = (0.0, 0.3, 0.7)  # Mostly 3-bet
            elif rank >= 7:  # 77-99
                ranges[label] = (0.1, 0.8, 0.1)  # Mostly call
            elif rank >= 4:  # 44-66
                ranges[label] = (0.3, 0.6, 0.1)  # Call some, fold some
            else:  # 22-33
                ranges[label] = (0.5, 0.4, 0.1)  # Fold more
        elif cls.kind == "suited":
            high = cls.high
            low = cls.low
            gap = high - low
            
            if high >= 11:  # AKs, AQs, AJs, KQs
                ranges[label] = (0.0, 0.2, 0.8)  # Mostly 3-bet
            elif high >= 8:  # Medium suited
                if gap <= 2:  # Connectors
                    ranges[label] = (0.2, 0.7, 0.1)
                else:
                    ranges[label] = (0.3, 0.6, 0.1)
            elif high >= 5:  # Low suited
                if gap <= 2:
                    ranges[label] = (0.3, 0.6, 0.1)
                else:
                    ranges[label] = (0.5, 0.4, 0.1)
            else:  # Very low
                ranges[label] = (0.7, 0.2, 0.1)
        else:  # offsuit
            high = cls.high
            low = cls.low
            
            if high >= 11:  # AKo, AQo, AJo
                ranges[label] = (0.1, 0.3, 0.6)
            elif high >= 9:  # KJo, QJo, JTo
                ranges[label] = (0.4, 0.5, 0.1)
            elif high >= 7:
                ranges[label] = (0.6, 0.3, 0.1)
            else:
                ranges[label] = (0.8, 0.1, 0.1)
    
    # Adjust based on villain position
    if villain_position == "UTG":
        # Tighten against UTG
        for label in ranges:
            fold, call, three_bet = ranges[label]
            ranges[label] = (min(1.0, fold + 0.15), call * 0.8, three_bet * 0.7)
    elif villain_position == "BTN":
        # Widen against BTN
        for label in ranges:
            fold, call, three_bet = ranges[label]
            ranges[label] = (max(0.0, fold - 0.1), call * 1.1, three_bet * 1.2)
    
    # Normalize
    for label in ranges:
        total = sum(ranges[label])
        if total > 0:
            ranges[label] = tuple(x / total for x in ranges[label])
    
    return ranges


def compute_bb_defense(
    villain_position: str,
    stack_depth: float = 100.0,
    open_size: float = 2.5,
) -> DefenseStrategy:
    """Compute BB defense strategy against a specific open.
    
    Uses GTO-approximate defense ranges.
    """
    classes = all_classes()
    n = len(classes)
    
    # Get defense ranges
    defense_ranges = _get_bb_defense_range_vs_position(villain_position)
    
    fold_freq = np.zeros(n)
    call_freq = np.zeros(n)
    three_bet_freq = np.zeros(n)
    
    for i, cls in enumerate(classes):
        label = cls.label
        if label in defense_ranges:
            fold_freq[i], call_freq[i], three_bet_freq[i] = defense_ranges[label]
        else:
            fold_freq[i] = 0.9
            call_freq[i] = 0.08
            three_bet_freq[i] = 0.02
    
    # Adjust for stack depth
    if stack_depth < 30:
        # Short stack - more 3-bet/fold, less call
        for i in range(n):
            if three_bet_freq[i] > 0.1:
                three_bet_freq[i] *= 1.3
                call_freq[i] *= 0.7
    elif stack_depth > 150:
        # Deep stack - more call (better implied odds)
        for i in range(n):
            if call_freq[i] > 0.1:
                call_freq[i] *= 1.2
                three_bet_freq[i] *= 0.9
    
    # Normalize
    for i in range(n):
        total = fold_freq[i] + call_freq[i] + three_bet_freq[i]
        if total > 0:
            fold_freq[i] /= total
            call_freq[i] /= total
            three_bet_freq[i] /= total
    
    # Calculate summary stats
    defense_freq = 1.0 - fold_freq.mean()
    three_bet_total = three_bet_freq.mean()
    call_total = call_freq.mean()
    
    explanation = _generate_defense_explanation(
        villain_position, stack_depth, defense_freq, three_bet_total, call_total
    )
    
    key_points = _generate_defense_key_points(
        villain_position, stack_depth, defense_freq
    )
    
    return DefenseStrategy(
        hero_position="BB",
        villain_position=villain_position,
        stack_depth=stack_depth,
        fold_freq=fold_freq,
        call_freq=call_freq,
        three_bet_freq=three_bet_freq,
        defense_freq=defense_freq,
        three_bet_freq_total=three_bet_total,
        call_freq_total=call_total,
        explanation=explanation,
        key_points=key_points,
    )


def compute_sb_defense(
    villain_position: str,
    stack_depth: float = 100.0,
    open_size: float = 2.5,
) -> DefenseStrategy:
    """Compute SB defense strategy against a BTN/CO open.
    
    SB is in a tough spot - out of position but has already posted 0.5bb.
    Should 3-bet more aggressively to take initiative.
    """
    classes = all_classes()
    n = len(classes)
    
    # Get BB defense ranges as base
    defense_ranges = _get_bb_defense_range_vs_position(villain_position)
    
    fold_freq = np.zeros(n)
    call_freq = np.zeros(n)
    three_bet_freq = np.zeros(n)
    
    for i, cls in enumerate(classes):
        label = cls.label
        if label in defense_ranges:
            f, c, t = defense_ranges[label]
            # SB should 3-bet more, call less
            fold_freq[i] = f
            call_freq[i] = c * 0.6  # Reduce calling
            three_bet_freq[i] = t * 1.5  # Increase 3-betting
        else:
            fold_freq[i] = 0.9
            call_freq[i] = 0.05
            three_bet_freq[i] = 0.05
    
    # Normalize
    for i in range(n):
        total = fold_freq[i] + call_freq[i] + three_bet_freq[i]
        if total > 0:
            fold_freq[i] /= total
            call_freq[i] /= total
            three_bet_freq[i] /= total
    
    # Calculate summary stats
    defense_freq = 1.0 - fold_freq.mean()
    three_bet_total = three_bet_freq.mean()
    call_total = call_freq.mean()
    
    explanation = _generate_defense_explanation(
        villain_position, stack_depth, defense_freq, three_bet_total, call_total,
        is_sb=True
    )
    
    key_points = _generate_defense_key_points(
        villain_position, stack_depth, defense_freq, is_sb=True
    )
    
    return DefenseStrategy(
        hero_position="SB",
        villain_position=villain_position,
        stack_depth=stack_depth,
        fold_freq=fold_freq,
        call_freq=call_freq,
        three_bet_freq=three_bet_freq,
        defense_freq=defense_freq,
        three_bet_freq_total=three_bet_total,
        call_freq_total=call_total,
        explanation=explanation,
        key_points=key_points,
    )


def _generate_defense_explanation(
    villain_pos: str,
    stack: float,
    defense_freq: float,
    three_bet_freq: float,
    call_freq: float,
    is_sb: bool = False,
) -> str:
    """Generate explanation for defense strategy."""
    position = "SB" if is_sb else "BB"
    
    explanation = f"{position}面对{villain_pos}开池的GTO防守策略：\n"
    explanation += f"- 防守频率: {defense_freq*100:.1f}% (弃牌{(1-defense_freq)*100:.1f}%)\n"
    explanation += f"- 跟注频率: {call_freq*100:.1f}%\n"
    explanation += f"- 3-bet频率: {three_bet_freq*100:.1f}%\n"
    
    if is_sb:
        explanation += "\n注意：SB位置不利，应更倾向于3-bet或弃牌，减少跟注。"
    
    return explanation


def _generate_defense_key_points(
    villain_pos: str,
    stack: float,
    defense_freq: float,
    is_sb: bool = False,
) -> list[str]:
    """Generate key points for defense strategy."""
    points = []
    
    position = "SB" if is_sb else "BB"
    
    if villain_pos == "BTN":
        points.append(f"BTN开池范围最宽，{position}应防守较宽")
    elif villain_pos == "CO":
        points.append(f"CO开池范围较宽，{position}可适当防守")
    elif villain_pos in ["UTG", "HJ"]:
        points.append(f"{villain_pos}开池范围紧，{position}应谨慎防守")
    
    if stack < 30:
        points.append("短筹码：推注范围更宽，跟注范围更窄")
    elif stack > 150:
        points.append("深筹码：隐含赔率更好，可多玩同花连牌")
    
    if defense_freq > 0.6:
        points.append("防守频率较高：用较宽范围跟注和3-bet")
    elif defense_freq < 0.4:
        points.append("防守频率较低：只用强牌防守")
    
    if is_sb:
        points.append("SB位置不利：优先3-bet或弃牌，减少被动跟注")
    
    return points


def get_defense_strategy_for_scenario(
    hero_position: str,
    villain_position: str,
    stack_depth: float = 100.0,
    open_size: float = 2.5,
) -> dict:
    """Get defense strategy formatted for the frontend."""
    if hero_position == "BB":
        defense = compute_bb_defense(villain_position, stack_depth, open_size)
    elif hero_position == "SB":
        defense = compute_sb_defense(villain_position, stack_depth, open_size)
    else:
        raise ValueError(f"Defense strategy not applicable for {hero_position}")
    
    classes = all_classes()
    strategies = {}
    
    for i, cls in enumerate(classes):
        actions = ["fold", "call", "3bet"]
        probs = [
            float(defense.fold_freq[i]),
            float(defense.call_freq[i]),
            float(defense.three_bet_freq[i]),
        ]
        action_kinds = ["fold", "check_call", "bet_100"]
        
        strategies[cls.label] = {
            "hand": cls.label,
            "actions": actions,
            "probs": probs,
            "action_kinds": action_kinds,
        }
    
    return {
        "strategies": strategies,
        "defense_freq": defense.defense_freq,
        "three_bet_freq": defense.three_bet_freq_total,
        "call_freq": defense.call_freq_total,
        "explanation": defense.explanation,
        "key_points": defense.key_points,
    }
