"""Multi-table poker strategy module.

Provides GTO-based strategies for 6-max and 7-max tables:
- Position-based opening ranges
- 3-bet/4-bet ranges
- Defense frequencies
- Postflop adjustments
"""

from strategy.positions import Position, get_position_name, get_relative_position
from strategy.ranges import OpeningRange, ThreeBetRange, get_opening_range, get_3bet_range
from strategy.scenarios import TableScenario, analyze_scenario

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
]
