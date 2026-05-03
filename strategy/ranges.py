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
    """Get GTO opening range for a position at a 6-max table.

    Args:
        position: Position to get range for
        stack_depth: Stack size in big blinds
        table_size: Reserved (6-max only)

    Returns:
        OpeningRange with hand frequencies
    """
    del table_size
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


# ============================================================
# Defense ranges (call + 3-bet) for facing an open
# ============================================================


@dataclass
class DefenseRange:
    """Hero's response to a single open: aggregate call & 3-bet frequencies."""
    hero_position: Position
    villain_position: Position
    raise_hands: dict[str, float] = field(default_factory=dict)  # 3-bet (value + bluff)
    call_hands: dict[str, float] = field(default_factory=dict)
    description: str = ""


# BB defense vs BTN open (2.5x, 100bb) — baseline for OOP defense.
# Each entry: (call_freq, raise_freq). Tuned so combo-weighted output
# vs BTN gives ~50% VPIP and ~13% 3-bet; tighter villains scale down both.
_BB_DEFENSE_BASELINE: dict[str, tuple[float, float]] = {
    # --- Premium 3-bet (always) ---
    "AA": (0.0, 1.0), "KK": (0.0, 1.0), "QQ": (0.0, 1.0),
    "AKs": (0.0, 1.0), "AKo": (0.0, 1.0),
    "JJ": (0.05, 0.95),
    # --- Strong mixed value ---
    "TT": (0.25, 0.75),
    "AQs": (0.05, 0.95), "AQo": (0.3, 0.7),
    "AJs": (0.2, 0.8), "ATs": (0.5, 0.5),
    "KQs": (0.25, 0.75), "KJs": (0.45, 0.55), "KTs": (0.7, 0.3),
    # --- Pairs (call + 3-bet for value/protection) ---
    "99": (0.45, 0.55), "88": (0.7, 0.3),
    "77": (0.85, 0.15), "66": (0.95, 0.05), "55": (1.0, 0.0),
    "44": (1.0, 0.0), "33": (1.0, 0.0), "22": (1.0, 0.0),
    # --- Suited aces (low-A polarized bluffs) ---
    "A9s": (0.6, 0.4), "A8s": (0.4, 0.6),
    "A7s": (0.3, 0.7), "A6s": (0.3, 0.7),
    "A5s": (0.0, 1.0), "A4s": (0.0, 1.0),
    "A3s": (0.2, 0.8), "A2s": (0.4, 0.6),
    # --- Suited kings/queens (mid-suited K as bluffs) ---
    "K9s": (0.55, 0.45), "K8s": (0.5, 0.5), "K7s": (0.55, 0.4),
    "K6s": (0.7, 0.25), "K5s": (0.7, 0.15), "K4s": (0.6, 0.0),
    "K3s": (0.45, 0.0), "K2s": (0.3, 0.0),
    "QJs": (0.95, 0.05), "QTs": (1.0, 0.0), "Q9s": (1.0, 0.0),
    "Q8s": (0.95, 0.0), "Q7s": (0.7, 0.0), "Q6s": (0.5, 0.0),
    "Q5s": (0.4, 0.0), "Q4s": (0.25, 0.0), "Q3s": (0.15, 0.0),
    # --- Suited jacks/tens ---
    "JTs": (1.0, 0.0), "J9s": (1.0, 0.0), "J8s": (0.9, 0.0),
    "J7s": (0.55, 0.0), "J6s": (0.3, 0.0), "J5s": (0.2, 0.0),
    "T9s": (1.0, 0.0), "T8s": (1.0, 0.0), "T7s": (0.75, 0.0),
    "T6s": (0.4, 0.0), "T5s": (0.2, 0.0),
    # --- Suited connectors / one-gappers ---
    "98s": (1.0, 0.0), "97s": (0.85, 0.0), "96s": (0.5, 0.0), "95s": (0.25, 0.0),
    "87s": (1.0, 0.0), "86s": (0.7, 0.0), "85s": (0.4, 0.0),
    "76s": (1.0, 0.0), "75s": (0.65, 0.0), "74s": (0.3, 0.0),
    "65s": (1.0, 0.0), "64s": (0.55, 0.0),
    "54s": (0.95, 0.0), "53s": (0.55, 0.0),
    "43s": (0.55, 0.0), "42s": (0.2, 0.0),
    "32s": (0.25, 0.0),
    # --- Offsuit broadways ---
    "AJo": (0.85, 0.15), "ATo": (1.0, 0.0),
    "A9o": (0.95, 0.05), "A8o": (0.7, 0.0),
    "A7o": (0.5, 0.0), "A6o": (0.4, 0.0),
    "A5o": (0.6, 0.0), "A4o": (0.4, 0.0),
    "A3o": (0.3, 0.0), "A2o": (0.25, 0.0),
    "KQo": (0.85, 0.15), "KJo": (0.9, 0.1),
    "KTo": (1.0, 0.0), "K9o": (0.8, 0.0), "K8o": (0.45, 0.0),
    "K7o": (0.25, 0.0), "K6o": (0.15, 0.0),
    "QJo": (0.95, 0.05), "QTo": (1.0, 0.0),
    "Q9o": (0.7, 0.0), "Q8o": (0.35, 0.0), "Q7o": (0.15, 0.0),
    "JTo": (1.0, 0.0), "J9o": (0.8, 0.0), "J8o": (0.45, 0.0),
    "J7o": (0.2, 0.0),
    # --- Offsuit connectors ---
    "T9o": (0.95, 0.0), "T8o": (0.55, 0.0), "T7o": (0.2, 0.0),
    "98o": (0.7, 0.0), "97o": (0.3, 0.0),
    "87o": (0.5, 0.0), "86o": (0.15, 0.0),
    "76o": (0.4, 0.0), "65o": (0.3, 0.0),
    "54o": (0.2, 0.0),
}


# Tightness multiplier (call freq) by villain position. BTN=baseline (1.0).
# Earlier opens are stronger -> defend less.
_DEFENSE_TIGHTNESS_BY_VILLAIN: dict[Position, float] = {
    Position.BTN: 1.0,
    Position.CO: 0.85,
    Position.HJ: 0.72,
    Position.UTG: 0.55,
    Position.SB: 1.15,  # SB raise is wider; BB defends wider in turn
}


def get_defense_range(
    hero: Position, villain: Position, stack_depth: float = 100.0
) -> DefenseRange:
    """Hero's call + 3-bet response to a single open.

    BB/SB use a wide OOP defense table scaled by villain tightness.
    IP positions cold-call rarely in GTO; we fall back to 3-bet-or-fold
    via :func:`get_3bet_range` plus a thin pair/broadway flat range.
    """
    is_oop = hero in (Position.BB, Position.SB)
    if not is_oop:
        return _ip_defense_range(hero, villain, stack_depth)

    tightness = _DEFENSE_TIGHTNESS_BY_VILLAIN.get(villain, 0.85)

    # SB defends slightly tighter (OOP postflop, dead 0.5bb already in)
    # but 3-bets more to deny equity. raise_boost partially offsets the
    # tightness scaling on raise_p.
    if hero == Position.SB:
        tightness *= 0.85
        raise_boost = 1.25
    else:
        raise_boost = 1.0

    # Tightness applies to BOTH calls and 3-bets — vs UTG opens we have
    # less fold equity AND fewer +EV calls, so both shrink.
    raise_scale = tightness * raise_boost

    raise_hands: dict[str, float] = {}
    call_hands: dict[str, float] = {}
    for hand, (call_p, raise_p) in _BB_DEFENSE_BASELINE.items():
        adj_raise = min(1.0, raise_p * raise_scale)
        adj_call = call_p * tightness
        if adj_call + adj_raise > 1.0:
            adj_call = max(0.0, 1.0 - adj_raise)
        if adj_raise > 1e-6:
            raise_hands[hand] = adj_raise
        if adj_call > 1e-6:
            call_hands[hand] = adj_call

    desc = f"{hero.value.upper()} defense vs {villain.value.upper()} open"
    return DefenseRange(
        hero_position=hero,
        villain_position=villain,
        raise_hands=raise_hands,
        call_hands=call_hands,
        description=desc,
    )


def _ip_defense_range(
    hero: Position, villain: Position, stack_depth: float
) -> DefenseRange:
    """IP cold-call vs open: thin pairs + broadways flat, 3-bet-or-fold elsewhere."""
    threebet = get_3bet_range(hero, villain, stack_depth)

    raise_hands: dict[str, float] = {}
    for h, f in threebet.value_hands.items():
        raise_hands[h] = max(raise_hands.get(h, 0.0), f)
    for h, f in threebet.bluff_hands.items():
        raise_hands[h] = max(raise_hands.get(h, 0.0), f)

    # IP cold-call is narrow even in GTO; mostly small/mid pairs and a few suited broadways.
    flat_baseline = {
        "TT": 0.5, "99": 0.7, "88": 0.7, "77": 0.7,
        "66": 0.6, "55": 0.5, "44": 0.4, "33": 0.3, "22": 0.3,
        "AJs": 0.4, "ATs": 0.6, "KQs": 0.5, "KJs": 0.4,
        "QJs": 0.5, "QTs": 0.4, "JTs": 0.5, "T9s": 0.4,
        "98s": 0.3, "87s": 0.2,
    }

    call_hands: dict[str, float] = {}
    for h, f in flat_baseline.items():
        # Don't let call overlap with the existing 3-bet on the same hand.
        cap = max(0.0, 1.0 - raise_hands.get(h, 0.0))
        if cap <= 0:
            continue
        call_hands[h] = min(f, cap)

    return DefenseRange(
        hero_position=hero,
        villain_position=villain,
        raise_hands=raise_hands,
        call_hands=call_hands,
        description=f"{hero.value.upper()} IP cold-call vs {villain.value.upper()} open",
    )
