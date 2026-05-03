"""Opening ranges for multi-table poker.

GTO-optimal opening ranges based on:
- Position
- Stack depth
- Table size
- Ante size

Ranges are represented as dict[str, float] where:
- key is hand class (e.g., "AA", "AKs", "AKo")
- value is opening frequency (0.0 to 1.0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from strategy.positions import Position


@dataclass
class OpeningRange:
    """Opening range for a position."""
    position: Position
    stack_depth: float = 100.0  # in big blinds
    
    # Hand frequencies (0.0 = never open, 1.0 = always open)
    hands: dict[str, float] = field(default_factory=dict)
    
    # Metadata
    vpip: float = 0.0  # Expected VPIP from this range
    description: str = ""


@dataclass
class ThreeBetRange:
    """3-bet range against a specific position."""
    hero_position: Position
    villain_position: Position
    
    # 3-bet frequencies by hand class
    value_hands: dict[str, float] = field(default_factory=dict)  # Always 3-bet for value
    bluff_hands: dict[str, float] = field(default_factory=dict)  # 3-bet as bluff
    call_hands: dict[str, float] = field(default_factory=dict)   # Just call
    
    description: str = ""


# ============================================================
# 6-Max Opening Ranges (100bb cash game, no ante)
# ============================================================

UTG_RANGE_100BB = {
    # Pairs
    "AA": 1.0, "KK": 1.0, "QQ": 1.0, "JJ": 1.0, "TT": 1.0,
    "99": 1.0, "88": 1.0, "77": 1.0, "66": 0.75, "55": 0.5,
    "44": 0.25, "33": 0.15, "22": 0.1,
    # Suited broadways
    "AKs": 1.0, "AQs": 1.0, "AJs": 1.0, "ATs": 1.0, "A9s": 0.75,
    "A8s": 0.5, "A7s": 0.4, "A6s": 0.3, "A5s": 0.5, "A4s": 0.4,
    "A3s": 0.2, "A2s": 0.15,
    "KQs": 1.0, "KJs": 1.0, "KTs": 0.75, "K9s": 0.4,
    "QJs": 1.0, "QTs": 0.75, "Q9s": 0.3,
    "JTs": 1.0, "J9s": 0.5,
    "T9s": 0.75, "T8s": 0.3,
    "98s": 0.5, "87s": 0.4, "76s": 0.3, "65s": 0.2,
    # Offsuit broadways
    "AKo": 1.0, "AQo": 1.0, "AJo": 0.75, "ATo": 0.4,
    "KQo": 0.75, "KJo": 0.5, "QJo": 0.4, "JTo": 0.3,
}

HJ_RANGE_100BB = {
    # Wider than UTG
    "AA": 1.0, "KK": 1.0, "QQ": 1.0, "JJ": 1.0, "TT": 1.0,
    "99": 1.0, "88": 1.0, "77": 1.0, "66": 1.0, "55": 0.75,
    "44": 0.5, "33": 0.35, "22": 0.25,
    # Suited aces wider
    "AKs": 1.0, "AQs": 1.0, "AJs": 1.0, "ATs": 1.0, "A9s": 1.0,
    "A8s": 0.75, "A7s": 0.6, "A6s": 0.5, "A5s": 0.75, "A4s": 0.6,
    "A3s": 0.4, "A2s": 0.3,
    # More suited connectors
    "KQs": 1.0, "KJs": 1.0, "KTs": 1.0, "K9s": 0.75,
    "QJs": 1.0, "QTs": 1.0, "Q9s": 0.5,
    "JTs": 1.0, "J9s": 0.75,
    "T9s": 1.0, "T8s": 0.5,
    "98s": 0.75, "87s": 0.6, "76s": 0.5, "65s": 0.4,
    # Offsuit wider
    "AKo": 1.0, "AQo": 1.0, "AJo": 1.0, "ATo": 0.75,
    "KQo": 1.0, "KJo": 0.75, "KTo": 0.4,
    "QJo": 0.75, "QTo": 0.3,
    "JTo": 0.5,
}

CO_RANGE_100BB = {
    # Significantly wider
    "AA": 1.0, "KK": 1.0, "QQ": 1.0, "JJ": 1.0, "TT": 1.0,
    "99": 1.0, "88": 1.0, "77": 1.0, "66": 1.0, "55": 1.0,
    "44": 0.75, "33": 0.6, "22": 0.5,
    # All suited aces
    "AKs": 1.0, "AQs": 1.0, "AJs": 1.0, "ATs": 1.0, "A9s": 1.0,
    "A8s": 1.0, "A7s": 1.0, "A6s": 0.75, "A5s": 1.0, "A4s": 0.75,
    "A3s": 0.6, "A2s": 0.5,
    # More suited hands
    "KQs": 1.0, "KJs": 1.0, "KTs": 1.0, "K9s": 1.0, "K8s": 0.5,
    "QJs": 1.0, "QTs": 1.0, "Q9s": 0.75, "Q8s": 0.4,
    "JTs": 1.0, "J9s": 1.0, "J8s": 0.5,
    "T9s": 1.0, "T8s": 0.75,
    "98s": 1.0, "87s": 0.75, "76s": 0.6, "65s": 0.5, "54s": 0.4,
    # Offsuit wider
    "AKo": 1.0, "AQo": 1.0, "AJo": 1.0, "ATo": 1.0, "A9o": 0.5,
    "KQo": 1.0, "KJo": 1.0, "KTo": 0.75,
    "QJo": 1.0, "QTo": 0.5,
    "JTo": 0.75, "T9o": 0.4,
}

BTN_RANGE_100BB = {
    # Very wide
    "AA": 1.0, "KK": 1.0, "QQ": 1.0, "JJ": 1.0, "TT": 1.0,
    "99": 1.0, "88": 1.0, "77": 1.0, "66": 1.0, "55": 1.0,
    "44": 1.0, "33": 1.0, "22": 1.0,
    # All suited aces and kings
    "AKs": 1.0, "AQs": 1.0, "AJs": 1.0, "ATs": 1.0, "A9s": 1.0,
    "A8s": 1.0, "A7s": 1.0, "A6s": 1.0, "A5s": 1.0, "A4s": 1.0,
    "A3s": 1.0, "A2s": 1.0,
    "KQs": 1.0, "KJs": 1.0, "KTs": 1.0, "K9s": 1.0, "K8s": 1.0,
    "K7s": 0.75, "K6s": 0.6, "K5s": 0.5, "K4s": 0.4, "K3s": 0.3, "K2s": 0.2,
    # Lots of suited connectors
    "QJs": 1.0, "QTs": 1.0, "Q9s": 1.0, "Q8s": 0.75, "Q7s": 0.5,
    "JTs": 1.0, "J9s": 1.0, "J8s": 0.75, "J7s": 0.4,
    "T9s": 1.0, "T8s": 1.0, "T7s": 0.5,
    "98s": 1.0, "97s": 0.75, "87s": 1.0, "86s": 0.5,
    "76s": 1.0, "75s": 0.6, "65s": 1.0, "64s": 0.5,
    "54s": 0.75, "53s": 0.4, "43s": 0.3,
    # Offsuit much wider
    "AKo": 1.0, "AQo": 1.0, "AJo": 1.0, "ATo": 1.0, "A9o": 1.0,
    "A8o": 0.75, "A7o": 0.6, "A6o": 0.5, "A5o": 0.75, "A4o": 0.5,
    "KQo": 1.0, "KJo": 1.0, "KTo": 1.0, "K9o": 0.75,
    "QJo": 1.0, "QTo": 1.0, "Q9o": 0.5,
    "JTo": 1.0, "J9o": 0.5,
    "T9o": 0.75, "98o": 0.5, "87o": 0.4,
}


def get_opening_range(position: Position, stack_depth: float = 100.0, table_size: int = 6) -> OpeningRange:
    """Get GTO opening range for a position.
    
    Args:
        position: Position to get range for
        stack_depth: Stack size in big blinds
        table_size: Number of players at table (6 or 7)
    
    Returns:
        OpeningRange with hand frequencies
    """
    # Select base range
    if position == Position.UTG:
        base = UTG_RANGE_100BB
        desc = "UTG开池范围 - 最紧，只玩强牌"
    elif position == Position.HJ:
        base = HJ_RANGE_100BB
        desc = "HJ开池范围 - 比UTG宽一些"
    elif position == Position.CO:
        base = CO_RANGE_100BB
        desc = "CO开池范围 - 较宽，好位置"
    elif position == Position.BTN:
        base = BTN_RANGE_100BB
        desc = "BTN开池范围 - 最宽，最佳位置"
    else:
        # SB/BB have different strategy (limp/defend)
        base = {}
        desc = f"{position.value} - 需要特殊策略"
    
    # Adjust for stack depth
    if stack_depth < 40:
        # Short stack - tighten up, remove small pairs and suited connectors
        adjusted = {h: f for h, f in base.items() if _is_short_stack_hand(h)}
    elif stack_depth > 150:
        # Deep stack - can play more speculative hands
        adjusted = {h: min(1.0, f * 1.1) for h, f in base.items()}
    else:
        adjusted = base.copy()
    
    # Calculate expected VPIP
    vpip = sum(adjusted.values()) / len(adjusted) if adjusted else 0
    
    return OpeningRange(
        position=position,
        stack_depth=stack_depth,
        hands=adjusted,
        vpip=vpip,
        description=desc,
    )


def _is_short_stack_hand(hand: str) -> bool:
    """Check if hand is playable with short stack."""
    # Remove small pairs
    if len(hand) == 2 and hand[0] == hand[1]:
        rank = "23456789TJQKA".index(hand[0])
        return rank >= 4  # 66+
    
    # Remove low suited connectors
    if hand.endswith("s"):
        high = "23456789TJQKA".index(hand[0])
        low = "23456789TJQKA".index(hand[1])
        return high >= 7 or (high - low <= 2 and high >= 4)  # Broadway or connectors 54s+
    
    # Offsuit - keep broadways
    high = "23456789TJQKA".index(hand[0])
    return high >= 8  # JT+


def get_3bet_range(hero: Position, villain: Position, stack_depth: float = 100.0) -> ThreeBetRange:
    """Get 3-bet range for hero against villain's open.
    
    Args:
        hero: Hero's position
        villain: Villain's position (who opened)
        stack_depth: Stack size in big blinds
    
    Returns:
        ThreeBetRange with value/bluff/call frequencies
    """
    # Value 3-bet hands (always 3-bet for value)
    value = {
        "AA": 1.0, "KK": 1.0, "QQ": 1.0, "AKs": 1.0, "AKo": 1.0,
    }
    
    # Add more value hands based on position
    if villain in [Position.UTG, Position.HJ]:
        # Against early position - tighter value range
        value["JJ"] = 0.75
        value["AQs"] = 0.5
    else:
        # Against late position - wider value range
        value["JJ"] = 1.0
        value["TT"] = 0.75
        value["AQs"] = 1.0
        value["AQo"] = 0.75
        value["AJs"] = 0.5
    
    # Bluff 3-bet hands (balance with value)
    bluffs = {}
    if villain in [Position.CO, Position.BTN]:
        # Bluff more against late position opens
        bluffs = {
            "A5s": 0.75, "A4s": 0.75, "A3s": 0.5,
            "K9s": 0.5, "Q9s": 0.4, "J9s": 0.3,
            "T9s": 0.3, "98s": 0.25, "87s": 0.2,
        }
    elif villain in [Position.HJ, Position.UTG]:
        # Less bluffing against early position
        bluffs = {
            "A5s": 0.4, "A4s": 0.3,
        }
    
    # Call hands (flat call instead of 3-bet)
    calls = {
        "QQ": 0.25,  # Sometimes trap with QQ
        "JJ": 0.25,  # Sometimes flat JJ
        "TT": 0.5,   # Often flat TT
        "99": 0.75,  # Usually flat medium pairs
        "88": 0.75,
        "77": 0.75,
        "AKs": 0.0,  # Always 3-bet AKs
        "AQs": 0.5,  # Sometimes flat AQs
        "AJs": 0.75,
        "KQs": 0.75,
    }
    
    desc = f"{hero.value} 3-bet vs {villain.value} open"
    if villain in [Position.CO, Position.BTN]:
        desc += " - 可以bluff更多"
    else:
        desc += " - 偏紧，以价值为主"
    
    return ThreeBetRange(
        hero_position=hero,
        villain_position=villain,
        value_hands=value,
        bluff_hands=bluffs,
        call_hands=calls,
        description=desc,
    )
