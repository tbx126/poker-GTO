"""Leak detection for poker players.

Analyzes hand histories to identify:
- Systematic strategy leaks
- Frequency deviations from GTO
- Situation-specific weaknesses
- Pattern-based leak detection
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from mda.storage import HandHistoryStore
from mda.profiler import PlayerProfile, PlayerProfiler


class LeakSeverity(Enum):
    """Severity of a detected leak."""
    LOW = "low"        # Minor deviation
    MEDIUM = "medium"  # Noticeable EV loss
    HIGH = "high"      # Significant EV loss
    CRITICAL = "critical"  # Major systematic leak


class LeakCategory(Enum):
    """Categories of leaks."""
    PREFLOP = "preflop"
    POSTFLOP = "postflop"
    BET_SIZING = "bet_sizing"
    BLUFFING = "bluffing"
    VALUE_BETTING = "value_betting"
    FOLDING = "folding"
    POSITION = "position"


@dataclass
class Leak:
    """A detected leak."""
    leak_id: str
    category: LeakCategory
    severity: LeakSeverity
    
    # Description
    title: str
    description: str
    
    # Evidence
    sample_size: int = 0
    devation_from_gto: float = 0.0  # How far from GTO
    
    # Metrics
    affected_hands: int = 0
    ev_loss_per_hand: float = 0.0
    total_ev_loss: float = 0.0
    
    # Recommendation
    recommendation: str = ""
    training_scenario_ids: list[str] = field(default_factory=list)


@dataclass
class LeakReport:
    """Report of detected leaks for a player."""
    player_name: str
    total_hands: int
    
    # Detected leaks
    leaks: list[Leak] = field(default_factory=list)
    
    # Summary
    total_ev_loss: float = 0.0
    worst_leak: Optional[Leak] = None
    
    # Recommendations
    priority_training: list[str] = field(default_factory=list)


class LeakDetector:
    """Detects leaks in player's poker game."""
    
    def __init__(self, store: HandHistoryStore):
        self.store = store
        self.profiler = PlayerProfiler(store)
    
    def detect_leaks(self, player_name: str, min_hands: int = 100) -> LeakReport:
        """Detect all leaks for a player.
        
        Args:
            player_name: Name of the player to analyze
            min_hands: Minimum hands required for analysis
            
        Returns:
            LeakReport with all detected leaks
        """
        # Get player profile
        profile = self.profiler.profile_player(player_name, min_hands)
        
        if not profile:
            return LeakReport(
                player_name=player_name,
                total_hands=0,
            )
        
        leaks = []
        
        # Check preflop leaks
        leaks.extend(self._check_preflop_leaks(profile))
        
        # Check aggression leaks
        leaks.extend(self._check_aggression_leaks(profile))
        
        # Check street-specific leaks
        leaks.extend(self._check_street_leaks(profile))
        
        # Sort by severity
        severity_order = {
            LeakSeverity.CRITICAL: 0,
            LeakSeverity.HIGH: 1,
            LeakSeverity.MEDIUM: 2,
            LeakSeverity.LOW: 3,
        }
        leaks.sort(key=lambda l: severity_order.get(l.severity, 4))
        
        # Calculate totals
        total_ev_loss = sum(l.total_ev_loss for l in leaks)
        worst_leak = leaks[0] if leaks else None
        
        # Generate priority training
        priority_training = self._generate_priority_training(leaks)
        
        return LeakReport(
            player_name=player_name,
            total_hands=profile.total_hands,
            leaks=leaks,
            total_ev_loss=total_ev_loss,
            worst_leak=worst_leak,
            priority_training=priority_training,
        )
    
    def _check_preflop_leaks(self, profile: PlayerProfile) -> list[Leak]:
        """Check for preflop leaks."""
        leaks = []
        
        # VPIP too high
        if profile.vpip > 0.35:
            leaks.append(Leak(
                leak_id="preflop_vpip_high",
                category=LeakCategory.PREFLOP,
                severity=LeakSeverity.HIGH,
                title="VPIP Too High",
                description=f"Playing {profile.vpip*100:.0f}% of hands (target: 18-25%)",
                sample_size=profile.total_hands,
                devation_from_gto=profile.vpip - 0.22,
                recommendation="Tighten opening range, especially from early position",
            ))
        
        # VPIP too low
        elif profile.vpip < 0.12:
            leaks.append(Leak(
                leak_id="preflop_vpip_low",
                category=LeakCategory.PREFLOP,
                severity=LeakSeverity.MEDIUM,
                title="VPIP Too Low",
                description=f"Only playing {profile.vpip*100:.0f}% of hands (target: 18-25%)",
                sample_size=profile.total_hands,
                devation_from_gto=0.18 - profile.vpip,
                recommendation="Widen opening range, add more speculative hands",
            ))
        
        # PFR too low (passive)
        if profile.pfr < profile.vpip * 0.6:
            leaks.append(Leak(
                leak_id="preflop_passive",
                category=LeakCategory.PREFLOP,
                severity=LeakSeverity.HIGH,
                title="Too Passive Preflop",
                description=f"VPIP ({profile.vpip*100:.0f}%) much higher than PFR ({profile.pfr*100:.0f}%)",
                sample_size=profile.total_hands,
                devation_from_gto=profile.vpip - profile.pfr,
                recommendation="Raise instead of limping, 3-bet more instead of calling",
            ))
        
        return leaks
    
    def _check_aggression_leaks(self, profile: PlayerProfile) -> list[Leak]:
        """Check for aggression-related leaks."""
        leaks = []
        
        # Too passive
        if profile.aggression_factor < 1.5:
            leaks.append(Leak(
                leak_id="aggression_low",
                category=LeakCategory.POSTFLOP,
                severity=LeakSeverity.HIGH,
                title="Not Aggressive Enough",
                description=f"Aggression factor {profile.aggression_factor:.1f} (target: 2.0-3.0)",
                sample_size=profile.total_hands,
                devation_from_gto=2.0 - profile.aggression_factor,
                recommendation="Bet and raise more instead of checking and calling",
            ))
        
        # Too aggressive
        elif profile.aggression_factor > 4.0:
            leaks.append(Leak(
                leak_id="aggression_high",
                category=LeakCategory.POSTFLOP,
                severity=LeakSeverity.MEDIUM,
                title="Overly Aggressive",
                description=f"Aggression factor {profile.aggression_factor:.1f} (target: 2.0-3.0)",
                sample_size=profile.total_hands,
                devation_from_gto=profile.aggression_factor - 3.0,
                recommendation="Add more check-call and call lines to balance",
            ))
        
        return leaks
    
    def _check_street_leaks(self, profile: PlayerProfile) -> list[Leak]:
        """Check for street-specific leaks."""
        leaks = []
        
        # River folding too much
        if profile.river.fold_freq > 0.6:
            leaks.append(Leak(
                leak_id="river_overfold",
                category=LeakCategory.FOLDING,
                severity=LeakSeverity.HIGH,
                title="Folding Too Much on River",
                description=f"River fold frequency {profile.river.fold_freq*100:.0f}% (target: <50%)",
                sample_size=profile.total_hands,
                devation_from_gto=profile.river.fold_freq - 0.5,
                recommendation="Call down lighter, trust your hand reading",
            ))
        
        # River too passive
        if profile.river.bet_freq < 0.2 and profile.river.raise_freq < 0.1:
            leaks.append(Leak(
                leak_id="river_passive",
                category=LeakCategory.VALUE_BETTING,
                severity=LeakSeverity.MEDIUM,
                title="Too Passive on River",
                description="Not value betting or raising enough on river",
                sample_size=profile.total_hands,
                recommendation="Value bet thinner, add bluff raises",
            ))
        
        # Flop cbet too low
        if profile.flop.bet_freq < 0.3:
            leaks.append(Leak(
                leak_id="flop_cbet_low",
                category=LeakCategory.BET_SIZING,
                severity=LeakSeverity.MEDIUM,
                title="Low Flop C-Bet Frequency",
                description=f"Flop bet frequency {profile.flop.bet_freq*100:.0f}% (target: 50-65%)",
                sample_size=profile.total_hands,
                devation_from_gto=0.5 - profile.flop.bet_freq,
                recommendation="C-bet more on favorable textures",
            ))
        
        return leaks
    
    def _generate_priority_training(self, leaks: list[Leak]) -> list[str]:
        """Generate priority training recommendations based on leaks."""
        training = []
        
        # Map leak categories to training scenarios
        category_training = {
            LeakCategory.PREFLOP: [
                "preflop_open_ranges",
                "preflop_3bet_strategy",
                "preflop_position_play",
            ],
            LeakCategory.POSTFLOP: [
                "flop_cbet_strategy",
                "turn_barrel_strategy",
                "river_value_bet",
            ],
            LeakCategory.BET_SIZING: [
                "bet_sizing_flop",
                "bet_sizing_turn",
                "bet_sizing_river",
            ],
            LeakCategory.BLUFFING: [
                "river_bluff_catch",
                "semi_bluff_draws",
                "balanced_ranges",
            ],
            LeakCategory.VALUE_BETTING: [
                "thin_value_bets",
                "value_bet_sizing",
                "river_value_ownership",
            ],
            LeakCategory.FOLDING: [
                "calling_stations",
                "river_call_downs",
                "pot_odds_training",
            ],
        }
        
        # Add training based on detected leaks
        for leak in leaks[:3]:  # Top 3 leaks
            category = leak.category
            if category in category_training:
                training.extend(category_training[category])
        
        # Remove duplicates
        return list(dict.fromkeys(training))
    
    def generate_sample_leak_report(self) -> LeakReport:
        """Generate a sample leak report for demonstration."""
        return LeakReport(
            player_name="SamplePlayer",
            total_hands=1000,
            leaks=[
                Leak(
                    leak_id="preflop_passive",
                    category=LeakCategory.PREFLOP,
                    severity=LeakSeverity.HIGH,
                    title="Too Passive Preflop",
                    description="VPIP 28% but PFR only 15% - limping too much",
                    sample_size=1000,
                    devation_from_gto=0.13,
                    affected_hands=130,
                    ev_loss_per_hand=0.05,
                    total_ev_loss=6.5,
                    recommendation="Raise instead of limping, 3-bet more instead of calling",
                    training_scenario_ids=["preflop_open", "preflop_3bet"],
                ),
                Leak(
                    leak_id="river_overfold",
                    category=LeakCategory.FOLDING,
                    severity=LeakSeverity.MEDIUM,
                    title="Folding Too Much on River",
                    description="River fold frequency 65% - exploitable by bluffs",
                    sample_size=1000,
                    devation_from_gto=0.15,
                    affected_hands=200,
                    ev_loss_per_hand=0.03,
                    total_ev_loss=6.0,
                    recommendation="Call down lighter with good blockers",
                    training_scenario_ids=["river_call", "bluff_catch"],
                ),
            ],
            total_ev_loss=12.5,
            priority_training=[
                "preflop_3bet_strategy",
                "river_call_downs",
                "pot_odds_training",
            ],
        )
