"""6-max position definitions (relative to button).

  BTN (Button) - best position, acts last postflop
  SB  (Small Blind) - acts first postflop, 0.5bb posted
  BB  (Big Blind) - acts second postflop, 1bb posted
  UTG (Under the Gun) - first to act preflop
  HJ  (Hijack) - middle position
  CO  (Cutoff) - good position, second-to-last preflop
"""

from __future__ import annotations

from enum import Enum


class Position(Enum):
    """Positions at a 6-max poker table."""
    BTN = "btn"    # Button
    SB = "sb"      # Small Blind
    BB = "bb"      # Big Blind
    UTG = "utg"    # Under the Gun
    HJ = "hj"      # Hijack
    CO = "co"      # Cutoff


# Preflop action order (worst to best preflop position)
POSITION_ORDER_6MAX = [Position.UTG, Position.HJ, Position.CO, Position.BTN, Position.SB, Position.BB]

# Position quality (higher = better postflop)
POSITION_QUALITY = {
    Position.BTN: 6,
    Position.CO: 5,
    Position.HJ: 4,
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
        Position.UTG: "最差的早期位置，需要最紧的范围。",
        Position.SB: "翻前最后行动，但翻后最差位置。需要谨慎。",
        Position.BB: "已经投入盲注，防守范围较宽。翻后最差位置之一。",
    }
    return descriptions.get(pos, "")


# Postflop action order (first to act → last to act). Higher index = IP.
_POSTFLOP_ORDER = [Position.SB, Position.BB, Position.UTG, Position.HJ, Position.CO, Position.BTN]


def get_relative_position(hero: Position, villain: Position) -> str:
    """Return "IP" if hero acts after villain postflop, else "OOP"."""
    return "IP" if _POSTFLOP_ORDER.index(hero) > _POSTFLOP_ORDER.index(villain) else "OOP"


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
