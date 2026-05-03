"""Position definitions for multi-table poker.

6-max positions (relative to button):
  BTN (Button) - Best position, acts last postflop
  SB (Small Blind) - Worst position, acts first postflop
  BB (Big Blind) - Acts first postflop, has invested blind
  UTG (Under the Gun) - First to act preflop
  HJ (Hijack) - Middle position
  CO (Cutoff) - Good position, second to last to act

7-max adds MP (Middle Position) between UTG and HJ.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Position(Enum):
    """Positions at a poker table."""
    BTN = "btn"    # Button
    SB = "sb"      # Small Blind
    BB = "bb"      # Big Blind
    UTG = "utg"    # Under the Gun
    UTG1 = "utg1"  # UTG+1 (7-max+)
    MP = "mp"      # Middle Position (7-max+)
    HJ = "hj"      # Hijack
    CO = "co"      # Cutoff


# Position order (preflop action order, worst to best)
POSITION_ORDER_6MAX = [Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB]
POSITION_ORDER_7MAX = [Position.UTG, Position.UTG1, Position.MP, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB]

# Position quality (higher = better)
POSITION_QUALITY = {
    Position.BTN: 6,
    Position.CO: 5,
    Position.HJ: 4,
    Position.MP: 3,
    Position.UTG1: 2,
    Position.UTG: 1,
    Position.SB: 0,
    Position.BB: 0,
}


def get_position_name(pos: Position) -> str:
    """Get display name for position."""
    names = {
        Position.BTN: "Button (BTN)",
        Position.SB: "Small Blind (SB)",
        Position.BB: "Big Blind (BB)",
        Position.UTG: "Under the Gun (UTG)",
        Position.UTG1: "UTG+1",
        Position.MP: "Middle Position (MP)",
        Position.HJ: "Hijack (HJ)",
        Position.CO: "Cutoff (CO)",
    }
    return names.get(pos, pos.value)


def get_position_description(pos: Position) -> str:
    """Get description of position characteristics."""
    descriptions = {
        Position.BTN: "最佳位置，翻后最后行动。可以玩最宽的范围。",
        Position.CO: "好位置，翻后倒数第二行动。可以较宽地开池。",
        Position.HJ: "中等位置，需要更紧的范围。",
        Position.MP: "中等位置，前面有人行动时需要更紧。",
        Position.UTG1: "差位置，前面只有UTG，需要紧的范围。",
        Position.UTG: "最差的早期位置，需要最紧的范围。",
        Position.SB: "翻前最后行动，但翻后最差位置。需要谨慎。",
        Position.BB: "已经投入盲注，防守范围较宽。翻后最差位置之一。",
    }
    return descriptions.get(pos, "")


def get_relative_position(hero: Position, villain: Position, table_size: int = 6) -> str:
    """Get relative position description between hero and villain.
    
    Returns:
        "IP" if hero is in position postflop
        "OOP" if hero is out of position postflop
    
    Note: Postflop position order (first to act = worst):
        SB -> BB -> UTG -> HJ -> CO -> BTN
    """
    # Postflop position order (first to act to last to act)
    postflop_order_6max = [Position.SB, Position.BB, Position.UTG, Position.HJ, Position.CO, Position.BTN]
    postflop_order_7max = [Position.SB, Position.BB, Position.UTG, Position.UTG1, Position.MP, Position.HJ, Position.CO, Position.BTN]
    
    order = postflop_order_6max if table_size == 6 else postflop_order_7max
    
    hero_idx = order.index(hero)
    villain_idx = order.index(villain)
    
    # Higher index = later position = IP
    if hero_idx > villain_idx:
        return "IP"
    else:
        return "OOP"


def get_ante_adjusted_range(base_range: dict, ante: float = 0.0) -> dict:
    """Adjust range based on ante size.
    
    Antes increase pot odds, allowing wider ranges.
    """
    if ante <= 0:
        return base_range
    
    # Calculate pot odds adjustment
    # With ante, there's more dead money to fight for
    ante_factor = 1.0 + (ante * 6) / 1.5  # Rough adjustment
    
    adjusted = {}
    for hand, freq in base_range.items():
        # Widen range proportionally
        adjusted[hand] = min(1.0, freq * ante_factor)
    
    return adjusted
