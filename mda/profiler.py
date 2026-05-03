"""Player profiling and behavior analysis.

Generates detailed player profiles from hand history data:
- Playing style classification (TAG, LAG, TP, LP)
- Tendency analysis by street
- Positional awareness metrics
- Leak detection
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from mda.storage import HandHistoryStore


class PlayStyle(Enum):
    """Player style classification."""
    TAG = "tight_aggressive"      # Tight, aggressive when playing
    LAG = "loose_aggressive"      # Loose, aggressive
    TP = "tight_passive"          # Tight, passive (calling station)
    LP = "loose_passive"          # Loose, passive (fish)
    UNKNOWN = "unknown"


@dataclass
class StreetTendencies:
    """Tendencies for a specific street."""
    check_freq: float = 0.0
    bet_freq: float = 0.0
    raise_freq: float = 0.0
    call_freq: float = 0.0
    fold_freq: float = 0.0
    avg_bet_size: float = 0.0  # As fraction of pot
    aggression_factor: float = 0.0


@dataclass
class PositionStats:
    """Statistics by position."""
    hands_played: int = 0
    vpip: float = 0.0
    pfr: float = 0.0
    three_bet: float = 0.0
    fold_to_three_bet: float = 0.0
    steal_attempt: float = 0.0
    fold_to_steal: float = 0.0


@dataclass
class PlayerProfile:
    """Complete player profile."""
    player_name: str
    total_hands: int = 0
    
    # Overall stats
    vpip: float = 0.0
    pfr: float = 0.0
    three_bet: float = 0.0
    aggression_factor: float = 0.0
    wtsd: float = 0.0  # Went to showdown
    w_sd: float = 0.0  # Won money at showdown
    
    # Style classification
    style: PlayStyle = PlayStyle.UNKNOWN
    
    # Street tendencies
    preflop: StreetTendencies = field(default_factory=StreetTendencies)
    flop: StreetTendencies = field(default_factory=StreetTendencies)
    turn: StreetTendencies = field(default_factory=StreetTendencies)
    river: StreetTendencies = field(default_factory=StreetTendencies)
    
    # Position stats
    btn_stats: PositionStats = field(default_factory=PositionStats)
    sb_stats: PositionStats = field(default_factory=PositionStats)
    bb_stats: PositionStats = field(default_factory=PositionStats)
    
    # Leak indicators
    leaks: list[str] = field(default_factory=list)
    
    # Raw data for further analysis
    custom_stats: dict = field(default_factory=dict)


class PlayerProfiler:
    """Generates player profiles from hand history data."""
    
    def __init__(self, store: HandHistoryStore):
        self.store = store
    
    def profile_player(self, player_name: str, min_hands: int = 50) -> Optional[PlayerProfile]:
        """Generate a complete player profile.
        
        Args:
            player_name: Name of the player to profile
            min_hands: Minimum hands required for reliable stats
            
        Returns:
            PlayerProfile or None if insufficient data
        """
        # Get basic stats
        stats = self.store.get_player_stats(player_name)
        
        if stats["total_hands"] < min_hands:
            return None
        
        profile = PlayerProfile(
            player_name=player_name,
            total_hands=stats["total_hands"],
            vpip=stats["vpip"],
            pfr=stats["pfr"],
            aggression_factor=stats["aggression_factor"],
        )
        
        # Calculate street tendencies
        profile.preflop = self._calculate_street_tendencies(player_name, "preflop")
        profile.flop = self._calculate_street_tendencies(player_name, "flop")
        profile.turn = self._calculate_street_tendencies(player_name, "turn")
        profile.river = self._calculate_street_tendencies(player_name, "river")
        
        # Classify play style
        profile.style = self._classify_style(profile)
        
        # Detect leaks
        profile.leaks = self._detect_leaks(profile)
        
        return profile
    
    def _calculate_street_tendencies(self, player_name: str, street: str) -> StreetTendencies:
        """Calculate tendencies for a specific street."""
        actions = self.store.get_player_actions(player_name)
        street_actions = [a for a in actions if a.get("street") == street]
        
        if not street_actions:
            return StreetTendencies()
        
        total = len(street_actions)
        checks = sum(1 for a in street_actions if a["action_type"] == "check")
        bets = sum(1 for a in street_actions if a["action_type"] == "bet")
        raises = sum(1 for a in street_actions if a["action_type"] == "raise")
        calls = sum(1 for a in street_actions if a["action_type"] == "call")
        folds = sum(1 for a in street_actions if a["action_type"] == "fold")
        
        # Calculate average bet size
        bet_sizes = [a["amount"] for a in street_actions if a["action_type"] in ("bet", "raise")]
        avg_bet = sum(bet_sizes) / len(bet_sizes) if bet_sizes else 0
        
        # Aggression factor for this street
        aggressive = bets + raises
        passive = calls if calls > 0 else 1
        af = aggressive / passive
        
        return StreetTendencies(
            check_freq=checks / total,
            bet_freq=bets / total,
            raise_freq=raises / total,
            call_freq=calls / total,
            fold_freq=folds / total,
            avg_bet_size=avg_bet,
            aggression_factor=af,
        )
    
    def _classify_style(self, profile: PlayerProfile) -> PlayStyle:
        """Classify player style based on VPIP and PFR."""
        vpip = profile.vpip
        pfr = profile.pfr
        af = profile.aggression_factor
        
        # Tight/Loose threshold
        tight_threshold = 0.20  # 20% VPIP
        # Aggressive/Passive threshold
        aggressive_threshold = 2.0
        
        if vpip < tight_threshold:
            if af > aggressive_threshold:
                return PlayStyle.TAG
            else:
                return PlayStyle.TP
        else:
            if af > aggressive_threshold:
                return PlayStyle.LAG
            else:
                return PlayStyle.LP
    
    def _detect_leaks(self, profile: PlayerProfile) -> list[str]:
        """Detect common leaks in player's game."""
        leaks = []
        
        # VPIP too high or too low
        if profile.vpip > 0.35:
            leaks.append("Playing too many hands (high VPIP)")
        elif profile.vpip < 0.12:
            leaks.append("Playing too few hands (low VPIP)")
        
        # VPIP/PFR gap too large (passive)
        gap = profile.vpip - profile.pfr
        if gap > 0.15:
            leaks.append("Too passive preflop (limping/calling too much)")
        
        # Low aggression
        if profile.aggression_factor < 1.5:
            leaks.append("Not aggressive enough (low AF)")
        
        # High aggression
        if profile.aggression_factor > 4.0:
            leaks.append("Overly aggressive (high AF)")
        
        # River tendencies
        if profile.river.fold_freq > 0.6:
            leaks.append("Folding too much on river")
        
        if profile.river.bet_freq < 0.2 and profile.river.raise_freq < 0.1:
            leaks.append("Too passive on river")
        
        return leaks
    
    def compare_players(self, player1: str, player2: str) -> dict:
        """Compare two players' profiles."""
        profile1 = self.profile_player(player1)
        profile2 = self.profile_player(player2)
        
        if not profile1 or not profile2:
            return {"error": "Insufficient data for one or both players"}
        
        return {
            "player1": player1,
            "player2": player2,
            "comparison": {
                "vpip": {"p1": profile1.vpip, "p2": profile2.vpip},
                "pfr": {"p1": profile1.pfr, "p2": profile2.pfr},
                "af": {"p1": profile1.aggression_factor, "p2": profile2.aggression_factor},
                "style": {"p1": profile1.style.value, "p2": profile2.style.value},
            },
            "p1_leaks": profile1.leaks,
            "p2_leaks": profile2.leaks,
        }
    
    def get_player_type_stats(self) -> dict:
        """Get distribution of player types in the database."""
        cursor = self.store.conn.cursor()
        
        # Get all players with enough hands
        cursor.execute("""
            SELECT player_name, COUNT(DISTINCT hand_id) as hand_count
            FROM players
            GROUP BY player_name
            HAVING hand_count >= 50
        """)
        
        players = cursor.fetchall()
        style_counts = defaultdict(int)
        
        for player_row in players:
            profile = self.profile_player(player_row["player_name"])
            if profile:
                style_counts[profile.style.value] += 1
        
        return dict(style_counts)
