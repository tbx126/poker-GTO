"""Multi-table poker strategy module.

Provides GTO-based strategies for 6-max tables:
- Position-based opening ranges
- 3-bet/4-bet ranges
- Defense frequencies using HU solver
- Postflop adjustments
"""

from strategy.positions import Position, get_position_name, get_relative_position
from strategy.ranges import OpeningRange, ThreeBetRange, get_opening_range, get_3bet_range
from strategy.scenarios import TableScenario, analyze_scenario
from strategy.defense import (
    DefenseStrategy,
    compute_bb_defense,
    compute_sb_defense,
    get_defense_strategy_for_scenario,
    estimate_opening_range,
)

__all__ = [
    "Position",
    "get_position_name",
    "get_relative_position",
    "OpeningRange",
    "ThreeBetRange",
    "get_opening_range",
    "get_3bet_range",
    "TableScenario",
    "analyze_scenario",
    "DefenseStrategy",
    "compute_bb_defense",
    "compute_sb_defense",
    "get_defense_strategy_for_scenario",
    "estimate_opening_range",
]
