"""Population-level analysis for MDA.

Analyzes aggregate behavior patterns across large hand history databases:
- Population tendencies by situation
- Exploit generation from population leaks
- GTO vs population deviation analysis
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from mda.storage import HandHistoryStore


@dataclass
class SituationTendency:
    """Population tendency for a specific situation."""
    situation: str
    sample_size: int
    
    # Action frequencies
    fold_freq: float = 0.0
    check_freq: float = 0.0
    call_freq: float = 0.0
    bet_freq: float = 0.0
    raise_freq: float = 0.0
    
    # Bet sizing tendencies
    avg_bet_size: float = 0.0  # As fraction of pot
    bet_size_distribution: dict[str, float] = field(default_factory=dict)
    
    # Deviation from GTO
    gto_deviation: float = 0.0  # How far from GTO strategy


@dataclass
class TendencyReport:
    """Report of population tendencies for a situation."""
    situation: str
    description: str
    
    # Key tendencies
    tendencies: list[SituationTendency] = field(default_factory=list)
    
    # Exploit recommendations
    exploits: list[str] = field(default_factory=list)
    
    # Confidence metrics
    confidence: float = 0.0  # 0-1, based on sample size
    
    # Raw data for visualization
    data: dict = field(default_factory=dict)


class PopulationAnalyzer:
    """Analyzes population-level tendencies from hand history data."""
    
    def __init__(self, store: HandHistoryStore):
        self.store = store
    
    def analyze_preflop_open(self, position: str = "BTN") -> TendencyReport:
        """Analyze population preflop opening tendencies.
        
        Args:
            position: Position to analyze (BTN, CO, MP, etc.)
        """
        cursor = self.store.conn.cursor()
        
        # Get all preflop raises from this position
        cursor.execute("""
            SELECT a.player_name, a.action_type, a.amount
            FROM actions a
            JOIN players p ON a.hand_id = p.hand_id AND a.player_name = p.player_name
            WHERE a.street = 'preflop'
            AND p.position = ?
            AND a.action_type IN ('fold', 'call', 'raise', 'bet')
        """, (position,))
        
        actions = cursor.fetchall()
        
        if not actions:
            return TendencyReport(
                situation=f"preflop_open_{position}",
                description=f"Preflop open from {position}",
                confidence=0.0,
            )
        
        # Calculate frequencies
        total = len(actions)
        folds = sum(1 for a in actions if a["action_type"] == "fold")
        calls = sum(1 for a in actions if a["action_type"] == "call")
        raises = sum(1 for a in actions if a["action_type"] in ("raise", "bet"))
        
        tendency = SituationTendency(
            situation=f"preflop_open_{position}",
            sample_size=total,
            fold_freq=folds / total,
            call_freq=calls / total,
            raise_freq=raises / total,
        )
        
        # Calculate confidence based on sample size
        confidence = min(1.0, total / 1000)  # Full confidence at 1000+ samples
        
        # Generate exploits
        exploits = self._generate_open_exploits(tendency)
        
        return TendencyReport(
            situation=f"preflop_open_{position}",
            description=f"Preflop open from {position}",
            tendencies=[tendency],
            exploits=exploits,
            confidence=confidence,
            data={"total_samples": total},
        )
    
    def analyze_bb_defend(self) -> TendencyReport:
        """Analyze BB defense tendencies vs different open sizes."""
        cursor = self.store.conn.cursor()
        
        # Get BB actions facing opens
        cursor.execute("""
            SELECT 
                a.player_name,
                a.action_type,
                a.amount,
                open_action.amount as open_size
            FROM actions a
            JOIN actions open_action ON a.hand_id = open_action.hand_id
            WHERE a.street = 'preflop'
            AND a.player_name IN (
                SELECT player_name FROM players WHERE position = 'BB'
            )
            AND open_action.action_type = 'raise'
            AND open_action.player_name != a.player_name
            AND a.action_type IN ('fold', 'call', 'raise')
        """)
        
        actions = cursor.fetchall()
        
        if not actions:
            return TendencyReport(
                situation="bb_defend",
                description="BB defense vs open",
                confidence=0.0,
            )
        
        # Group by open size
        size_groups = defaultdict(list)
        for action in actions:
            open_size = action.get("open_size", 0)
            if open_size:
                # Normalize to BB
                size_key = f"{open_size:.1f}bb"
                size_groups[size_key].append(action)
        
        tendencies = []
        exploits = []
        
        for size_key, group in size_groups.items():
            total = len(group)
            folds = sum(1 for a in group if a["action_type"] == "fold")
            calls = sum(1 for a in group if a["action_type"] == "call")
            raises = sum(1 for a in group if a["action_type"] == "raise")
            
            tendency = SituationTendency(
                situation=f"bb_vs_{size_key}_open",
                sample_size=total,
                fold_freq=folds / total,
                call_freq=calls / total,
                raise_freq=raises / total,
            )
            tendencies.append(tendency)
            
            # Generate exploits for this sizing
            if folds / total > 0.7:
                exploits.append(f"Population over-folds BB vs {size_key} open - increase bluff frequency")
            elif calls / total > 0.5:
                exploits.append(f"Population over-calls BB vs {size_key} open - value bet thinner")
        
        confidence = min(1.0, len(actions) / 500)
        
        return TendencyReport(
            situation="bb_defend",
            description="BB defense vs open",
            tendencies=tendencies,
            exploits=exploits,
            confidence=confidence,
            data={"total_samples": len(actions)},
        )
    
    def analyze_cbet(self, street: str = "flop") -> TendencyReport:
        """Analyze continuation bet tendencies."""
        cursor = self.store.conn.cursor()
        
        # Get all cbet situations (preflop raiser, first to act on flop)
        cursor.execute("""
            SELECT 
                a.player_name,
                a.action_type,
                a.amount,
                h.board
            FROM actions a
            JOIN hands h ON a.hand_id = h.hand_id
            WHERE a.street = ?
            AND a.sequence_order = (
                SELECT MIN(a2.sequence_order) 
                FROM actions a2 
                WHERE a2.hand_id = a.hand_id AND a2.street = ?
            )
            AND a.player_name IN (
                SELECT DISTINCT a3.player_name 
                FROM actions a3 
                WHERE a3.hand_id = a.hand_id 
                AND a3.street = 'preflop' 
                AND a3.action_type = 'raise'
            )
        """, (street, street))
        
        actions = cursor.fetchall()
        
        if not actions:
            return TendencyReport(
                situation=f"cbet_{street}",
                description=f"Continuation bet on {street}",
                confidence=0.0,
            )
        
        total = len(actions)
        checks = sum(1 for a in actions if a["action_type"] == "check")
        bets = sum(1 for a in actions if a["action_type"] in ("bet", "raise"))
        
        tendency = SituationTendency(
            situation=f"cbet_{street}",
            sample_size=total,
            check_freq=checks / total,
            bet_freq=bets / total,
        )
        
        exploits = []
        if bets / total > 0.75:
            exploits.append(f"Population cbets {street} too frequently - increase check-raise bluff frequency")
        elif bets / total < 0.4:
            exploits.append(f"Population cbets {street} too infrequently - fold more to cbets")
        
        confidence = min(1.0, total / 300)
        
        return TendencyReport(
            situation=f"cbet_{street}",
            description=f"Continuation bet on {street}",
            tendencies=[tendency],
            exploits=exploits,
            confidence=confidence,
            data={"total_samples": total},
        )
    
    def analyze_river_call(self) -> TendencyReport:
        """Analyze river calling tendencies."""
        cursor = self.store.conn.cursor()
        
        # Get river calls/folds facing bets
        cursor.execute("""
            SELECT 
                a.player_name,
                a.action_type,
                a.amount,
                bet_action.amount as bet_size
            FROM actions a
            JOIN actions bet_action ON a.hand_id = bet_action.hand_id
            WHERE a.street = 'river'
            AND bet_action.street = 'river'
            AND bet_action.action_type = 'bet'
            AND bet_action.player_name != a.player_name
            AND a.action_type IN ('fold', 'call', 'raise')
        """)
        
        actions = cursor.fetchall()
        
        if not actions:
            return TendencyReport(
                situation="river_call",
                description="River calling tendencies",
                confidence=0.0,
            )
        
        # Group by bet size
        size_groups = defaultdict(list)
        for action in actions:
            bet_size = action.get("bet_size", 0)
            pot_size = 10  # Would need to calculate from hand data
            if bet_size and pot_size:
                ratio = bet_size / pot_size
                if ratio < 0.5:
                    size_key = "small"
                elif ratio < 1.0:
                    size_key = "medium"
                else:
                    size_key = "large"
                size_groups[size_key].append(action)
        
        tendencies = []
        exploits = []
        
        for size_key, group in size_groups.items():
            total = len(group)
            folds = sum(1 for a in group if a["action_type"] == "fold")
            calls = sum(1 for a in group if a["action_type"] == "call")
            raises = sum(1 for a in group if a["action_type"] == "raise")
            
            tendency = SituationTendency(
                situation=f"river_vs_{size_key}_bet",
                sample_size=total,
                fold_freq=folds / total,
                call_freq=calls / total,
                raise_freq=raises / total,
            )
            tendencies.append(tendency)
            
            if folds / total > 0.65:
                exploits.append(f"Population over-folds river vs {size_key} bet - bluff more")
            elif calls / total > 0.5:
                exploits.append(f"Population over-calls river vs {size_key} bet - value bet thinner")
        
        confidence = min(1.0, len(actions) / 200)
        
        return TendencyReport(
            situation="river_call",
            description="River calling tendencies",
            tendencies=tendencies,
            exploits=exploits,
            confidence=confidence,
            data={"total_samples": len(actions)},
        )
    
    def generate_exploit_strategy(self, situation: str) -> dict:
        """Generate an exploit strategy for a situation based on population data.
        
        Args:
            situation: Situation to generate exploit for
            
        Returns:
            Dict with exploit strategy recommendations
        """
        if situation == "preflop_open":
            report = self.analyze_preflop_open("BTN")
        elif situation == "bb_defend":
            report = self.analyze_bb_defend()
        elif situation == "cbet":
            report = self.analyze_cbet("flop")
        elif situation == "river_call":
            report = self.analyze_river_call()
        else:
            return {"error": f"Unknown situation: {situation}"}
        
        return {
            "situation": report.situation,
            "description": report.description,
            "confidence": report.confidence,
            "exploits": report.exploits,
            "tendencies": [
                {
                    "situation": t.situation,
                    "sample_size": t.sample_size,
                    "fold_freq": t.fold_freq,
                    "call_freq": t.call_freq,
                    "raise_freq": t.raise_freq,
                }
                for t in report.tendencies
            ],
        }
    
    def _generate_open_exploits(self, tendency: SituationTendency) -> list[str]:
        """Generate exploits for preflop open tendencies."""
        exploits = []
        
        if tendency.fold_freq > 0.6:
            exploits.append("Population folds too much from this position - widen opening range")
        elif tendency.raise_freq > 0.4:
            exploits.append("Population opens too wide - 3-bet for value more often")
        
        if tendency.call_freq > 0.2:
            exploits.append("Population limps too much - raise for isolation")
        
        return exploits
    
    def get_population_summary(self) -> dict:
        """Get summary of population tendencies across all situations."""
        cursor = self.store.conn.cursor()
        
        # Total hands
        cursor.execute("SELECT COUNT(*) as total FROM hands")
        total_hands = cursor.fetchone()["total"]
        
        # Total players
        cursor.execute("SELECT COUNT(DISTINCT player_name) as total FROM players")
        total_players = cursor.fetchone()["total"]
        
        # Average stats
        cursor.execute("""
            SELECT 
                AVG(CASE WHEN action_type IN ('call', 'raise', 'bet') THEN 1.0 ELSE 0.0 END) as avg_vpip,
                AVG(CASE WHEN action_type IN ('raise', 'bet') THEN 1.0 ELSE 0.0 END) as avg_pfr
            FROM actions
            WHERE street = 'preflop'
        """)
        avg_stats = cursor.fetchone()
        
        return {
            "total_hands": total_hands,
            "total_players": total_players,
            "avg_vpip": avg_stats["avg_vpip"] if avg_stats else 0,
            "avg_pfr": avg_stats["avg_pfr"] if avg_stats else 0,
        }
