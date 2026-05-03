"""Feedback engine for GTO training.

Provides real-time feedback on player decisions:
- Correct/incorrect classification
- EV loss calculation
- Strategy comparison with GTO
- Detailed explanations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from trainer.scenario import Scenario


class FeedbackType(Enum):
    """Types of feedback."""
    CORRECT = "correct"
    INCORRECT = "incorrect"
    CLOSE = "close"  # Within acceptable range
    SUBOPTIMAL = "suboptimal"  # Not GTO but reasonable


@dataclass
class Feedback:
    """Feedback on a player's decision."""
    feedback_type: FeedbackType
    player_action: str
    gto_action: str
    
    # EV analysis
    player_ev: float = 0.0
    gto_ev: float = 0.0
    ev_loss: float = 0.0  # gto_ev - player_ev
    
    # Strategy comparison
    player_strategy: dict[str, float] = field(default_factory=dict)
    gto_strategy: dict[str, float] = field(default_factory=dict)
    
    # Explanation
    explanation: str = ""
    key_points: list[str] = field(default_factory=list)
    
    # Correct action frequency in GTO
    gto_frequency: float = 0.0  # How often GTO takes this action


class FeedbackEngine:
    """Provides feedback on player decisions."""
    
    def __init__(self, tolerance: float = 0.05):
        """Initialize feedback engine.
        
        Args:
            tolerance: Acceptable deviation from GTO (as fraction)
        """
        self.tolerance = tolerance
    
    def analyze_decision(
        self,
        scenario: Scenario,
        player_action: str,
        gto_strategy: Optional[dict[str, float]] = None,
    ) -> Feedback:
        """Analyze a player's decision and provide feedback.
        
        Args:
            scenario: The training scenario
            player_action: The action the player chose
            gto_strategy: GTO strategy for comparison (from scenario if not provided)
            
        Returns:
            Feedback object with analysis
        """
        strategy = gto_strategy or scenario.gto_strategy
        
        if not strategy:
            # No GTO reference - generate basic feedback
            return Feedback(
                feedback_type=FeedbackType.CLOSE,
                player_action=player_action,
                gto_action="unknown",
                explanation="No GTO reference available for this scenario.",
            )
        
        # Find the GTO-preferred action
        gto_action = max(strategy, key=strategy.get)
        gto_freq = strategy.get(player_action, 0.0)
        
        # Determine feedback type
        if player_action == gto_action:
            feedback_type = FeedbackType.CORRECT
        elif gto_freq > self.tolerance:
            feedback_type = FeedbackType.CLOSE
        elif self._is_reasonable_alternative(player_action, gto_action, strategy):
            feedback_type = FeedbackType.SUBOPTIMAL
        else:
            feedback_type = FeedbackType.INCORRECT
        
        # Calculate EV loss (simplified)
        ev_loss = self._estimate_ev_loss(player_action, strategy)
        
        # Generate explanation
        explanation = self._generate_explanation(
            scenario, player_action, gto_action, strategy, feedback_type
        )
        
        # Key points
        key_points = self._generate_key_points(scenario, strategy)
        
        return Feedback(
            feedback_type=feedback_type,
            player_action=player_action,
            gto_action=gto_action,
            ev_loss=ev_loss,
            player_strategy={player_action: 1.0},
            gto_strategy=strategy,
            explanation=explanation,
            key_points=key_points,
            gto_frequency=gto_freq,
        )
    
    def _is_reasonable_alternative(
        self, player_action: str, gto_action: str, strategy: dict[str, float]
    ) -> bool:
        """Check if player's action is a reasonable alternative."""
        # Check if the action has reasonable frequency in GTO
        player_freq = strategy.get(player_action, 0.0)
        gto_freq = strategy.get(gto_action, 0.0)
        
        # If player's action is at least 20% as frequent as GTO action
        return player_freq > gto_freq * 0.2
    
    def _estimate_ev_loss(self, action: str, strategy: dict[str, float]) -> float:
        """Estimate EV loss from deviation from GTO.
        
        Simplified calculation - in production would use actual EV calculations.
        """
        # Find best action EV (assumed to be 0 for normalization)
        best_ev = 0.0
        
        # Estimate EV based on strategy frequency
        # Actions with higher GTO frequency are assumed to have higher EV
        action_freq = strategy.get(action, 0.0)
        max_freq = max(strategy.values())
        
        # Simple linear approximation
        ev_loss = (max_freq - action_freq) / max_freq * 0.5
        
        return max(0.0, ev_loss)
    
    def _generate_explanation(
        self,
        scenario: Scenario,
        player_action: str,
        gto_action: str,
        strategy: dict[str, float],
        feedback_type: FeedbackType,
    ) -> str:
        """Generate explanation for the feedback."""
        if feedback_type == FeedbackType.CORRECT:
            return f"Correct! {gto_action} is the GTO-optimal action."
        
        elif feedback_type == FeedbackType.CLOSE:
            gto_freq = strategy.get(player_action, 0.0) * 100
            return (
                f"Close, but {gto_action} is preferred. "
                f"Your action ({player_action}) is GTO {gto_freq:.0f}% of the time."
            )
        
        elif feedback_type == FeedbackType.SUBOPTIMAL:
            return (
                f"Suboptimal. While {player_action} can be played, "
                f"{gto_action} is significantly better in this spot."
            )
        
        else:  # INCORRECT
            gto_freq = strategy.get(gto_action, 0.0) * 100
            return (
                f"Incorrect. {gto_action} is the GTO action ({gto_freq:.0f}% frequency). "
                f"{player_action} loses too much EV."
            )
    
    def _generate_key_points(self, scenario: Scenario, strategy: dict[str, float]) -> list[str]:
        """Generate key learning points."""
        points = []
        
        # Sort actions by frequency
        sorted_actions = sorted(strategy.items(), key=lambda x: x[1], reverse=True)
        
        # Top 2 actions
        if len(sorted_actions) >= 2:
            action1, freq1 = sorted_actions[0]
            action2, freq2 = sorted_actions[1]
            
            points.append(f"Primary action: {action1} ({freq1*100:.0f}%)")
            
            if freq2 > 0.1:
                points.append(f"Secondary action: {action2} ({freq2*100:.0f}%)")
        
        # Situation-specific points
        if "preflop" in [t for t in scenario.tags]:
            points.append("Preflop decisions set the foundation for the hand")
        
        if "flop" in [t for t in scenario.tags]:
            points.append("Flop play is crucial for establishing range advantage")
        
        return points
    
    def batch_analyze(
        self, scenarios: list[Scenario], actions: list[str]
    ) -> list[Feedback]:
        """Analyze multiple decisions at once."""
        if len(scenarios) != len(actions):
            raise ValueError("Number of scenarios must match number of actions")
        
        return [
            self.analyze_decision(scenario, action)
            for scenario, action in zip(scenarios, actions)
        ]
    
    def calculate_accuracy(self, feedbacks: list[Feedback]) -> dict:
        """Calculate accuracy metrics from feedback list."""
        if not feedbacks:
            return {"accuracy": 0.0, "total": 0}
        
        correct = sum(1 for f in feedbacks if f.feedback_type == FeedbackType.CORRECT)
        close = sum(1 for f in feedbacks if f.feedback_type == FeedbackType.CLOSE)
        total = len(feedbacks)
        
        accuracy = (correct + close * 0.5) / total
        avg_ev_loss = sum(f.ev_loss for f in feedbacks) / total
        
        return {
            "accuracy": accuracy,
            "correct": correct,
            "close": close,
            "incorrect": total - correct - close,
            "total": total,
            "avg_ev_loss": avg_ev_loss,
        }
