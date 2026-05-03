"""MDA (Mass Data Analysis) module for poker hand history analysis.

Provides:
- Hand history parsing and storage
- Player profiling and behavior analysis
- Statistical aggregation for population tendencies
- Exploit generation from real-world data
"""

from mda.parser import HandHistory, parse_hand_history
from mda.storage import HandHistoryStore
from mda.profiler import PlayerProfile, PlayerProfiler
from mda.analyzer import PopulationAnalyzer, TendencyReport

__all__ = [
    "HandHistory",
    "parse_hand_history",
    "HandHistoryStore",
    "PlayerProfile",
    "PlayerProfiler",
    "PopulationAnalyzer",
    "TendencyReport",
]
