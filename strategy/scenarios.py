"""Scenario analysis for multi-table poker.

Provides analysis of specific situations:
- Preflop decisions
- Facing opens
- 3-bet/4-bet scenarios
- Postflop adjustments
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from strategy.positions import Position, get_position_name, get_relative_position
from strategy.ranges import (
    OpeningRange,
    ThreeBetRange,
    get_opening_range,
    get_3bet_range,
)


class Action(Enum):
    """Possible preflop actions."""
    FOLD = "fold"
    CALL = "call"
    RAISE_2X = "raise_2x"      # Min raise
    RAISE_25X = "raise_2.5x"   # Standard open
    RAISE_3X = "raise_3x"      # 3x raise
    RAISE_4X = "raise_4x"      # 4x raise (3-bet sizing)
    ALL_IN = "all_in"


@dataclass
class TableScenario:
    """A specific poker scenario at a multi-table game."""
    
    # Table setup
    table_size: int = 6
    ante: float = 0.0
    effective_stack: float = 100.0  # in big blinds
    
    # Hero info
    hero_position: Position = Position.BTN
    hero_hand: str = ""  # e.g., "AKs", "TT"
    
    # Action history
    raiser_position: Optional[Position] = None  # Who opened
    raise_size: float = 2.5  # Open size in BB
    callers: list[Position] = field(default_factory=list)
    
    # 3-bet/4-bet scenario
    three_bettor: Optional[Position] = None
    three_bet_size: float = 9.0  # 3-bet size in BB
    four_bettor: Optional[Position] = None
    four_bet_size: float = 25.0  # 4-bet size in BB


@dataclass
class ScenarioAnalysis:
    """Analysis result for a scenario."""
    
    scenario: TableScenario
    
    # Recommended action
    recommended_action: Action = Action.FOLD
    action_frequency: float = 0.0  # How often to take this action
    
    # All action frequencies
    action_frequencies: dict[str, float] = field(default_factory=dict)
    
    # Explanation
    explanation: str = ""
    key_points: list[str] = field(default_factory=list)
    
    # Range info
    hand_in_range: bool = False
    range_percentile: float = 0.0  # Where this hand falls in range (0=worst, 100=best)


def analyze_scenario(scenario: TableScenario) -> ScenarioAnalysis:
    """Analyze a poker scenario and provide GTO recommendation.
    
    Args:
        scenario: The poker scenario to analyze
    
    Returns:
        ScenarioAnalysis with recommendation
    """
    hero = scenario.hero_position
    hand = scenario.hero_hand
    
    # Case 1: No one has opened - Hero is first to act
    if scenario.raiser_position is None:
        return _analyze_open(scenario)
    
    # Case 2: Someone opened, Hero needs to respond
    if scenario.three_bettor is None:
        return _analyze_face_open(scenario)
    
    # Case 3: There was a 3-bet, Hero needs to respond
    if scenario.four_bettor is None:
        return _analyze_face_3bet(scenario)
    
    # Case 4: There was a 4-bet
    return _analyze_face_4bet(scenario)


def _analyze_open(scenario: TableScenario) -> ScenarioAnalysis:
    """Analyze opening scenario (no one has opened yet)."""
    hero = scenario.hero_position
    hand = scenario.hero_hand
    
    # Get opening range for position
    opening_range = get_opening_range(hero, scenario.effective_stack, scenario.table_size)
    
    # Check if hand is in range
    freq = opening_range.hands.get(hand, 0.0)
    
    if freq >= 0.9:
        action = Action.RAISE_25X
        explanation = f"标准开池。{hand}在{get_position_name(hero)}是强牌，应该100%开池。"
        points = [
            f"开池到2.5BB是标准尺寸",
            f"这个位置的开池范围约占{opening_range.vpip*100:.0f}%的手牌",
            "保持激进，争取翻前拿下底池",
        ]
    elif freq >= 0.5:
        action = Action.RAISE_25X
        explanation = f"可以开池。{hand}在{get_position_name(hero)}是可玩的手牌。"
        points = [
            f"开池频率约为{freq*100:.0f}%",
            "根据桌况调整：如果后面玩家很激进，可以收紧",
        ]
    elif freq > 0:
        action = Action.RAISE_25X if freq > 0.3 else Action.FOLD
        explanation = f"边际决定。{hand}在{get_position_name(hero)}是边缘手牌。"
        points = [
            f"开池频率约为{freq*100:.0f}%",
            "如果桌况较紧，可以开池；如果后面很激进，建议弃牌",
        ]
    else:
        action = Action.FOLD
        explanation = f"弃牌。{hand}不在{get_position_name(hero)}的开池范围内。"
        points = [
            "这手牌太弱，不适合在这个位置开池",
            "等待更好的位置或更强的手牌",
        ]
    
    return ScenarioAnalysis(
        scenario=scenario,
        recommended_action=action,
        action_frequency=freq,
        action_frequencies={"fold": 1 - freq, "open": freq},
        explanation=explanation,
        key_points=points,
        hand_in_range=freq > 0,
        range_percentile=freq * 100,
    )


def _analyze_face_open(scenario: TableScenario) -> ScenarioAnalysis:
    """Analyze facing an open raise."""
    hero = scenario.hero_position
    villain = scenario.raiser_position
    hand = scenario.hero_hand
    
    # Get 3-bet range
    three_bet_range = get_3bet_range(hero, villain, scenario.effective_stack)
    
    # Check if hand is value 3-bet
    value_freq = three_bet_range.value_hands.get(hand, 0.0)
    bluff_freq = three_bet_range.bluff_hands.get(hand, 0.0)
    call_freq = three_bet_range.call_hands.get(hand, 0.0)
    
    # Determine best action
    if value_freq > 0.5:
        action = Action.RAISE_4X  # 3-bet for value
        freq = value_freq
        explanation = f"3-bet for value! {hand}对抗{get_position_name(villain)}的开池是强牌。"
        points = [
            f"3-bet到{scenario.raise_size * 3.5:.0f}BB (约3.5x开池尺寸)",
            "这是价值3-bet，希望建立底池",
            "如果被4-bet，根据筹码深度决定",
        ]
    elif bluff_freq > 0.3:
        action = Action.RAISE_4X  # 3-bet bluff
        freq = bluff_freq
        explanation = f"3-bet bluff。{hand}可以作为bluff 3-bet来平衡范围。"
        points = [
            f"3-bet频率约为{bluff_freq*100:.0f}%",
            "这手牌有不错的可玩性（同花/连牌潜力）",
            "被跟注后翻后要谨慎",
        ]
    elif call_freq > 0.3:
        action = Action.CALL
        freq = call_freq
        explanation = f"跟注。{hand}适合跟注对抗{get_position_name(villain)}的开池。"
        points = [
            f"跟注频率约为{call_freq*100:.0f}%",
            "这手牌有足够的胜率/隐含赔率来跟注",
            "注意位置劣势（如果不在BTN）",
        ]
    else:
        action = Action.FOLD
        freq = 0.0
        explanation = f"弃牌。{hand}对抗{get_position_name(villain)}的开池太弱。"
        points = [
            "这手牌不在防守范围内",
            "等待更好的机会",
        ]
    
    return ScenarioAnalysis(
        scenario=scenario,
        recommended_action=action,
        action_frequency=freq,
        action_frequencies={
            "fold": max(0, 1 - value_freq - bluff_freq - call_freq),
            "call": call_freq,
            "3bet_value": value_freq,
            "3bet_bluff": bluff_freq,
        },
        explanation=explanation,
        key_points=points,
        hand_in_range=(value_freq + bluff_freq + call_freq) > 0,
        range_percentile=(value_freq + bluff_freq + call_freq) * 100,
    )


def _analyze_face_3bet(scenario: TableScenario) -> ScenarioAnalysis:
    """Analyze facing a 3-bet."""
    hero = scenario.hero_position
    hand = scenario.hero_hand
    three_bettor = scenario.three_bettor
    
    # Premium hands - always 4-bet or call
    premium_4bet = {"AA": 1.0, "KK": 1.0, "AKs": 1.0}
    strong_call = {"QQ": 0.75, "JJ": 0.5, "AKo": 0.75, "AQs": 0.5}
    
    if hand in premium_4bet:
        action = Action.RAISE_4X
        freq = premium_4bet[hand]
        explanation = f"4-bet! {hand}是绝对强牌，对抗3-bet应该4-bet。"
        points = [
            "这是最强的手牌之一",
            "4-bet到底池的2.5-3倍",
            "准备跟注对手的all-in",
        ]
    elif hand in strong_call:
        action = Action.CALL
        freq = strong_call[hand]
        explanation = f"跟注3-bet。{hand}足够强来对抗3-bet。"
        points = [
            "这手牌有很好的胜率",
            "跟注比4-bet更合适（避免被5-bet陷入困境）",
            "翻后要谨慎，特别是面对A高牌面",
        ]
    else:
        action = Action.FOLD
        freq = 0.0
        explanation = f"弃牌。{hand}对抗3-bet太弱。"
        points = [
            "3-bet范围通常很强",
            "不要用弱牌跟注3-bet",
        ]
    
    return ScenarioAnalysis(
        scenario=scenario,
        recommended_action=action,
        action_frequency=freq,
        action_frequencies={"fold": 1 - freq, "call": freq * 0.5, "4bet": freq * 0.5},
        explanation=explanation,
        key_points=points,
        hand_in_range=freq > 0,
        range_percentile=freq * 100,
    )


def _analyze_face_4bet(scenario: TableScenario) -> ScenarioAnalysis:
    """Analyze facing a 4-bet."""
    hand = scenario.hero_hand
    
    # Only AA and KK should continue against 4-bet
    if hand == "AA":
        action = Action.ALL_IN
        explanation = "All-in! AA是绝对最强手牌。"
        points = ["永远不要慢打AA对抗4-bet", "直接推all-in"]
    elif hand == "KK":
        action = Action.CALL  # Or ALL_IN depending on stack depth
        explanation = "跟注4-bet。KK很强，但要小心AA。"
        points = [
            "KK对抗4-bet范围有约65%的胜率",
            "如果筹码很深，可以跟注",
            "如果筹码较浅（<50BB），考虑直接推all-in",
        ]
    elif hand == "AKs":
        action = Action.CALL
        explanation = "跟注4-bet。AKs是很好的手牌。"
        points = [
            "AKs对抗QQ+/AK有约40%的胜率",
            "跟注比推all-in更好（保留翻后可玩性）",
        ]
    else:
        action = Action.FOLD
        explanation = f"弃牌。{hand}对抗4-bet太弱。"
        points = [
            "4-bet范围非常强（通常是QQ+, AK）",
            "除非有特殊读牌，否则弃牌",
        ]
    
    return ScenarioAnalysis(
        scenario=scenario,
        recommended_action=action,
        explanation=explanation,
        key_points=points,
        hand_in_range=action != Action.FOLD,
    )


def get_scenario_description(scenario: TableScenario) -> str:
    """Get human-readable description of scenario."""
    parts = []
    
    # Table info
    parts.append(f"{scenario.table_size}人桌")
    if scenario.ante > 0:
        parts.append(f"前注{scenario.ante}BB")
    parts.append(f"有效筹码{scenario.effective_stack}BB")
    
    # Hero info
    parts.append(f"你在{get_position_name(scenario.hero_position)}持{scenario.hero_hand}")
    
    # Action history
    if scenario.raiser_position:
        parts.append(f"{get_position_name(scenario.raiser_position)}开池到{scenario.raise_size}BB")
    
    if scenario.three_bettor:
        parts.append(f"{get_position_name(scenario.three_bettor)} 3-bet到{scenario.three_bet_size}BB")
    
    if scenario.four_bettor:
        parts.append(f"{get_position_name(scenario.four_bettor)} 4-bet到{scenario.four_bet_size}BB")
    
    return "，".join(parts)


def get_common_scenarios() -> list[TableScenario]:
    """Get list of common scenarios for training."""
    scenarios = []
    
    # BTN open
    scenarios.append(TableScenario(
        table_size=6, hero_position=Position.BTN, hero_hand="AKs",
        description="BTN持AKs，无人开池",
    ))
    
    # BB defend vs BTN open
    scenarios.append(TableScenario(
        table_size=6, hero_position=Position.BB, hero_hand="KQs",
        raiser_position=Position.BTN, raise_size=2.5,
        description="BB持KQs面对BTN开池",
    ))
    
    # CO 3-bet vs UTG open
    scenarios.append(TableScenario(
        table_size=6, hero_position=Position.CO, hero_hand="QQ",
        raiser_position=Position.UTG, raise_size=2.5,
        description="CO持QQ面对UTG开池",
    ))
    
    # BTN 4-bet vs CO 3-bet
    scenarios.append(TableScenario(
        table_size=6, hero_position=Position.BTN, hero_hand="AKo",
        raiser_position=Position.HJ, raise_size=2.5,
        three_bettor=Position.CO, three_bet_size=9.0,
        description="BTN持AKo，HJ开池，CO 3-bet",
    ))
    
    return scenarios
